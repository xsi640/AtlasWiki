"""Markdown/frontmatter 读写、页面命名与原子写入。"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter

from atlaswiki.config import config_store
from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.schema import (
    PAGE_TYPE_DIRS,
    PageStatus,
    PageType,
    normalize_page_name,
    validate_page_frontmatter,
)

from .links import LinkIndex, WikiLink, build_link_index, extract_links
from .vault import create_vault, ensure_inside_vault, safe_relative_path

# wiki 根目录文件是系统文件，不进入普通页面命名空间。
RESERVED_PAGE_NAMES = {"index", "log", "overview", "conventions"}


def utc_now() -> str:
    """返回 ISO8601 UTC 时间，符合架构 §5.2。"""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class MarkdownDocument:
    """frontmatter + Markdown 正文的通用载体。"""

    metadata: dict[str, Any]
    content: str
    relative_path: Path | None = None


@dataclass(slots=True)
class Page:
    """解析后的 wiki 页面。"""

    name: str
    metadata: dict[str, Any]
    content: str
    relative_path: Path
    links: list[WikiLink] = field(default_factory=list)

    @property
    def title(self) -> str:
        return str(self.metadata.get("title", self.name))

    @property
    def page_type(self) -> PageType:
        return PageType(self.metadata["type"])


@dataclass(frozen=True, slots=True)
class PageDraft:
    """新建或更新页面时的输入。"""

    name: str
    title: str
    page_type: PageType | str
    source_type: str
    zone: str = ""
    content: str = ""
    human_edited: bool = False
    status: PageStatus | str = PageStatus.ACTIVE
    origin_source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """同目录临时文件 + fsync + os.replace，目标文件永远不会出现半截内容。"""

    target.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, target)
        # 目录项也需要持久化，极端断电场景下 replace 才可靠。
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def serialize_markdown(document: MarkdownDocument) -> bytes:
    """用 python-frontmatter 序列化；保留字段顺序并支持中文。"""

    post = frontmatter.Post(document.content, **document.metadata)
    text = frontmatter.dumps(post, sort_keys=False, allow_unicode=True)
    return text.encode("utf-8")


class WikiStore:
    """vault 内 Markdown 的读写与 wiki 页面链接索引。"""

    def __init__(self, vault: str | Path, *, initialized: bool = False) -> None:
        self.vault = Path(vault).expanduser().resolve()
        if initialized:
            create_vault(self.vault)

    @classmethod
    def from_config(cls) -> WikiStore:
        """从冻结的配置契约读取 vault 路径。"""

        configured = config_store.load().vault_path
        if not configured:
            raise AppError(ErrorCode.VALIDATION, "尚未配置 vault 路径")
        return cls(configured)

    @property
    def wiki_dir(self) -> Path:
        return self.vault / "wiki"

    def initialize(self) -> Path:
        """创建或补齐 vault 骨架。"""

        return create_vault(self.vault)

    @property
    def initialized(self) -> bool:
        """判断骨架是否已经可用。"""

        return self.vault.is_dir() and self.wiki_dir.is_dir()

    def resolve_path(self, relative_path: str | Path) -> Path:
        """返回 vault 内安全绝对路径。"""

        return ensure_inside_vault(self.vault, relative_path)

    def read_markdown(self, relative_path: str | Path) -> MarkdownDocument:
        """读取任意 vault 内 Markdown，路径越界或文件缺失会抛业务异常。"""

        safe = safe_relative_path(relative_path)
        path = self.resolve_path(safe)
        if not path.is_file():
            raise AppError(ErrorCode.NOT_FOUND, "Markdown 文件不存在", {"path": str(safe)})
        try:
            post = frontmatter.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as exc:
            raise AppError(ErrorCode.PARSE_FAILED, "Markdown 读取失败", {"path": str(safe)}) from exc
        return MarkdownDocument(metadata=post.metadata, content=post.content, relative_path=safe)

    def write_markdown(
        self,
        relative_path: str | Path,
        metadata: dict[str, Any],
        content: str,
        *,
        expected_updated_at: str | None = None,
        update_timestamp: bool = False,
    ) -> MarkdownDocument:
        """写前读取最新版本，然后原子写 Markdown。"""

        safe = safe_relative_path(relative_path)
        if safe.suffix.lower() != ".md":
            raise AppError(ErrorCode.VALIDATION, "只允许写入 .md 文件", {"path": str(safe)})
        target = self.resolve_path(safe)

        current: MarkdownDocument | None = None
        if target.exists():
            current = self.read_markdown(safe)
            if expected_updated_at is not None and current.metadata.get("updated_at") != expected_updated_at:
                raise AppError(
                    ErrorCode.SOURCE_BUSY,
                    "页面已被其他任务更新，请基于最新版本重写",
                    {"path": str(safe), "expected_updated_at": expected_updated_at},
                )

        output_metadata = dict(metadata)
        if update_timestamp:
            current_metadata = current.metadata if current is not None else {}
            output_metadata["created_at"] = current_metadata.get(
                "created_at",
                metadata.get("created_at") or utc_now(),
            )
            output_metadata["updated_at"] = utc_now()
        document = MarkdownDocument(metadata=output_metadata, content=content, relative_path=safe)
        atomic_write_bytes(target, serialize_markdown(document))
        return document

    def page_path(self, name: str, page_type: PageType | str) -> Path:
        """根据页面类型返回规范化的相对路径。"""

        normalized = normalize_page_name(name)
        if not normalized:
            raise AppError(ErrorCode.VALIDATION, "页面名不能为空", {"name": name})
        if normalized in RESERVED_PAGE_NAMES:
            raise AppError(ErrorCode.VALIDATION, "页面名与系统文件冲突", {"name": normalized})
        page_type_value = PageType(page_type)
        return Path("wiki") / PAGE_TYPE_DIRS[page_type_value] / f"{normalized}.md"

    def write_page(self, draft: PageDraft, *, overwrite: bool = True) -> Page:
        """校验、计算 links 字段并原子写页面。"""

        name = normalize_page_name(draft.name)
        page_type = PageType(draft.page_type)
        metadata = {
            **draft.metadata,
            "title": draft.title,
            "type": page_type.value,
            "source_type": draft.source_type,
            "zone": draft.zone,
            "human_edited": draft.human_edited,
            "status": PageStatus(draft.status).value,
            "origin_source": draft.origin_source,
        }
        errors = validate_page_frontmatter(metadata)
        if errors:
            raise AppError(ErrorCode.VALIDATION, "frontmatter 校验失败", {"fields": errors})

        relative_path = self.page_path(name, page_type)
        target = self.resolve_path(relative_path)
        if target.exists() and not overwrite:
            raise AppError(ErrorCode.VALIDATION, "页面已存在", {"name": name})

        # links 是由正文解析结果回写的权威字段，不接受调用方单独声明。
        parsed_links = extract_links(draft.content)
        metadata["links"] = list(dict.fromkeys(link.target for link in parsed_links))
        self.write_markdown(relative_path, metadata, draft.content, update_timestamp=True)
        return self.read_page(name)

    def _scan_page_paths(self) -> dict[str, Path]:
        """按 stem 扫描四个页面目录，重复页面名会被视为数据错误。"""

        if not self.wiki_dir.is_dir():
            return {}
        pages: dict[str, Path] = {}
        for _page_type, directory in PAGE_TYPE_DIRS.items():
            page_dir = self.wiki_dir / directory
            if not page_dir.is_dir():
                continue
            for path in page_dir.glob("*.md"):
                name = path.stem
                if name in RESERVED_PAGE_NAMES:
                    continue
                if name in pages:
                    raise AppError(
                        ErrorCode.VALIDATION,
                        "页面名在不同类型目录中重复",
                        {"name": name, "paths": [str(pages[name]), str(path)]},
                    )
                pages[name] = path
        return pages

    def read_page(self, name: str) -> Page:
        """读取一个页面名对应的最新文件。"""

        normalized = normalize_page_name(name)
        path = self._scan_page_paths().get(normalized)
        if path is None:
            raise AppError(ErrorCode.NOT_FOUND, "页面不存在", {"name": normalized})
        relative_path = path.relative_to(self.vault)
        document = self.read_markdown(relative_path)
        return Page(
            name=normalized,
            metadata=document.metadata,
            content=document.content,
            relative_path=relative_path,
            links=extract_links(document.content),
        )

    def read_pages(self) -> list[Page]:
        """读取全部 wiki 页面，按页面名排序。"""

        pages = [self.read_page(name) for name in sorted(self._scan_page_paths())]
        return pages

    def list_page_names(self) -> list[str]:
        """返回页面名索引。"""

        return sorted(self._scan_page_paths())

    def link_index(self) -> LinkIndex:
        """构建全库链接索引。"""

        names = self.list_page_names()
        return build_link_index(names, {page.name: [link.target for link in page.links] for page in self.read_pages()})

    def out_links(self, name: str) -> list[str]:
        """返回页面唯一出链目标。"""

        return self.link_index().out_links.get(normalize_page_name(name), [])

    def back_links(self, name: str) -> list[str]:
        """返回引用该页面的来源页面。"""

        return self.link_index().back_links.get(normalize_page_name(name), [])

    def outlinks(self, name: str) -> list[str]:
        """out_links 的语义别名。"""

        return self.out_links(name)

    def backlinks(self, name: str) -> list[str]:
        """back_links 的语义别名。"""

        return self.back_links(name)
