"""Wiki 存储与链接层（MODULE-003）公共导出。"""

from .links import LinkIndex, WikiLink, build_link_index, extract_links
from .store import (
    RESERVED_PAGE_NAMES,
    MarkdownDocument,
    Page,
    PageDraft,
    WikiStore,
    atomic_write_bytes,
    serialize_markdown,
)
from .vault import VAULT_DIRECTORIES, create_vault, ensure_inside_vault, safe_relative_path

__all__ = [
    "VAULT_DIRECTORIES",
    "LinkIndex",
    "MarkdownDocument",
    "Page",
    "PageDraft",
    "RESERVED_PAGE_NAMES",
    "WikiLink",
    "WikiStore",
    "atomic_write_bytes",
    "build_link_index",
    "create_vault",
    "ensure_inside_vault",
    "extract_links",
    "safe_relative_path",
    "serialize_markdown",
]
