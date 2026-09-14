"""文本处理工具：中文分词、关键词抽取、HTML 正文提取与 Markdown 转换。"""

from __future__ import annotations

import re
from typing import Iterable

import jieba
import jieba.analyse
from bs4 import BeautifulSoup, NavigableString, Tag

# jieba 首次调用会构建前缀词典，这里显式初始化一次，避免首个请求变慢
jieba.initialize()

_WS_RE = re.compile(r"[ \t\u00a0]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")

STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "及", "也", "就", "都", "而", "但", "或",
    "一个", "我们", "你们", "他们", "这个", "那个", "什么", "怎么", "如何", "可以",
    "没有", "自己", "因为", "所以", "如果", "还是", "已经", "进行", "通过", "以及",
    "这些", "那些", "一些", "不是", "就是", "可能", "需要", "使用", "用于", "包括",
    "例如", "比如", "但是", "然而", "因此", "并且", "或者", "其他", "其中", "对于",
    "这样", "那样", "之后", "之前", "同时", "主要", "非常", "一种", "一样", "时候",
    "页面", "部分", "方式", "情况", "方面", "一般", "基本", "相关", "有关", "上述",
    "如下", "以下", "总之", "由于", "根据", "关于", "作为", "成为", "具有", "存在",
}

# 英文停用词（TF-IDF 对英文不敏感，必须自己过滤）
EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than", "that", "this",
    "these", "those", "there", "here", "when", "where", "which", "who", "whom",
    "what", "why", "how", "all", "any", "both", "each", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "so", "too", "very", "can",
    "will", "just", "should", "now", "also", "into", "onto", "upon", "about",
    "above", "after", "again", "against", "because", "before", "below", "between",
    "during", "from", "further", "have", "has", "had", "having", "was", "were",
    "are", "been", "being", "does", "did", "doing", "done", "not", "nor", "off",
    "out", "over", "under", "until", "while", "with", "without", "within",
    "would", "could", "shall", "may", "might", "must", "however", "therefore",
    "thus", "hence", "moreover", "furthermore", "nevertheless", "although",
    "though", "whether", "either", "neither", "one", "two", "three", "first",
    "second", "third", "many", "much", "like", "unlike", "include", "includes",
    "including", "included", "used", "using", "use", "uses", "based", "given",
    "made", "make", "makes", "making", "take", "takes", "taken", "see", "sees",
    "seen", "known", "well", "often", "always", "sometimes", "usually",
    "generally", "typically", "commonly", "particularly", "especially", "e.g",
    "i.e", "etc", "via", "per", "new", "old", "good", "best", "better", "large",
    "larger", "largest", "small", "smaller", "high", "higher", "low", "lower",
    "however", "rather", "instead", "example", "examples", "case", "cases",
    "type", "types", "kind", "kinds", "form", "forms", "way", "ways", "time",
    "times", "year", "years", "day", "days", "part", "parts", "number", "numbers",
    "system", "systems", "method", "methods", "approach", "approaches",
    "result", "results", "problem", "problems", "process", "processes",
    "article", "articles", "page", "pages", "text", "texts", "word", "words",
    "http", "https", "www", "com", "org", "net", "html", "pdf", "doi",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday",
    "never", "always", "give", "gives", "given", "get", "gets", "got", "go",
    "goes", "went", "come", "comes", "came", "say", "says", "said", "know",
    "knows", "knew", "think", "thinks", "thought", "want", "wants", "wanted",
    "need", "needs", "needed", "find", "finds", "found", "tell", "tells", "told",
    "work", "works", "worked", "call", "calls", "called", "let", "lets", "put",
    "puts", "keep", "keeps", "kept", "begin", "begins", "began", "show", "shows",
    "shown", "hear", "hears", "heard", "play", "plays", "played", "run", "runs",
    "ran", "move", "moves", "moved", "live", "lives", "lived", "believe",
    "bring", "happen", "happens", "write", "writes", "written", "provide",
    "provides", "provided", "read", "reads", "read", "consider", "appear",
    "appears", "note", "notes", "noted", "allow", "allows", "allowed",
    "still", "even", "ever", "yet", "back", "down", "end", "ends", "ended",
    "first", "last", "next", "long", "short", "great", "little", "right",
    "left", "same", "different", "important", "possible", "available",
    "however", "upon", "among", "along", "across", "behind", "beyond",
    "according", "template", "retrieved", "archived", "isbn", "doi", "url",
    "urn", "arxiv", "pmid", "wikipedia", "wikimedia", "edit", "source",
    "archived", "citation", "cite", "ref", "refs", "footnote", "category",
    "categories", "disambiguation", "stub", "portal", "series", "sidebar",
}

_ASCII_RE = re.compile(r"^[0-9a-zA-Z][0-9a-zA-Z+#._-]*$")
_PROPER_RE = re.compile(
    r"\b([A-Z][a-zA-Z0-9]*(?:[ -][A-Z][a-zA-Z0-9]*){0,3})\b"
)
_PROPER_BLOCK = {
    "the", "a", "an", "in", "on", "of", "for", "and", "or", "to", "with",
    "this", "that", "these", "those", "it", "its", "as", "at", "by", "from",
    "we", "you", "they", "he", "she", "i", "however", "although", "because",
    "when", "where", "which", "who", "what", "why", "how", "if", "then",
    "there", "here", "one", "two", "three", "first", "second", "third",
    # 句首常见的普通词，容易在抽取时被误当成专有名词
    "template", "according", "also", "additionally", "furthermore", "moreover",
    "therefore", "thus", "hence", "note", "see", "references", "external",
    "retrieved", "archived", "isbn", "doi", "url", "urn", "arxiv", "pmid",
    "using", "used", "based", "given", "since", "while", "after", "before",
    "during", "until", "unless", "whether", "both", "each", "every", "some",
    "any", "all", "most", "many", "much", "more", "less", "other", "another",
    "such", "same", "different", "new", "old", "due", "per", "via", "etc",
    "volume", "issue", "pages", "no", "vol", "edition", "press", "university",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}

# 出现在专有名词短语开头时可以安全丢掉的限定词
_LEAD_ARTICLES = {
    "the", "a", "an", "this", "that", "these", "those", "its", "our",
    "their", "his", "her", "my", "your", "some", "any", "all", "each", "every",
}


def _keep_token(token: str) -> bool:
    if not token or len(token) < 2:
        return False
    if token in STOPWORDS or token in EN_STOPWORDS:
        return False
    if _ASCII_RE.match(token):
        # 英文/数字词：至少 4 个字符，且不能是纯数字
        if len(token) < 4 or token.isdigit():
            return False
    return True


def _normalize(term: str) -> str:
    """轻量归一：英文去复数、去首尾符号。"""
    term = term.strip().strip("-_.")
    if _ASCII_RE.match(term) and len(term) > 4 and term.endswith("s") and not term.endswith("ss"):
        stem = term[:-1]
        if stem in EN_STOPWORDS:
            return term
        return stem
    return term


def _proper_noun_phrases(text: str, limit: int = 60) -> list[str]:
    """抽取英文专有名词/术语短语，这是英文语料里最像「概念」的东西。"""
    counts: dict[str, int] = {}
    for match in _PROPER_RE.finditer(text):
        phrase = match.group(1).strip()
        words = phrase.split()
        # 丢掉句首限定词：'An LLM' -> 'LLM'
        while words and words[0].lower() in _LEAD_ARTICLES:
            words.pop(0)
        if not words:
            continue
        phrase = " ".join(words)
        if len(phrase) < 3:
            continue
        lowered = [w.lower() for w in words]
        # 整段都是停用词 / 功能词，跳过
        if all(w in _PROPER_BLOCK or w in EN_STOPWORDS for w in lowered):
            continue
        # 单个词：要求是缩写（全大写）或长度足够，且不是常见词
        if len(words) == 1:
            if phrase.isupper():
                if len(phrase) < 2:
                    continue
            elif len(phrase) < 6 or phrase.lower() in EN_STOPWORDS:
                continue
        counts[phrase] = counts.get(phrase, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0])))
    return [term for term, count in ranked if count >= 2][:limit]


def _looks_like_acronym(term: str) -> bool:
    core = term[:-1] if (term.endswith("s") and len(term) > 2) else term
    return len(core) >= 2 and core.isupper() and core.isascii()


def keywords(text: str, top_n: int = 8) -> list[str]:
    """抽取关键词/概念。中文走 TF-IDF，英文走专有名词短语。"""
    if not text or len(text) < 30:
        return []

    cleaned: list[str] = []
    seen: set[str] = set()

    def push(raw: str, *, from_proper: bool) -> None:
        term = (raw or "").strip()
        if not _keep_token(term):
            return
        if _ASCII_RE.match(term) and not from_proper:
            # 英文普通词：太短的几乎都是 noise（model / data / technique）
            if not _looks_like_acronym(term) and len(term) < 7:
                return
        term = _normalize(term)
        if not _keep_token(term):
            return
        key = term.lower()
        if key in seen:
            return
        seen.add(key)
        cleaned.append(term)

    # 1) 英文专有名词短语优先（LLM、RAG、Large Language Model 这类）
    for phrase in _proper_noun_phrases(text):
        push(phrase, from_proper=True)
        if len(cleaned) >= top_n * 2:
            break

    # 2) 中文 TF-IDF
    try:
        tags = jieba.analyse.extract_tags(text, topK=top_n * 4, withWeight=False)
    except Exception:
        tags = []
    for tag in tags:
        push(tag, from_proper=False)
        if len(cleaned) >= top_n:
            break

    return cleaned[:top_n]


# --------------------------------------------------------------------------- #
# 清洗与分块
# --------------------------------------------------------------------------- #

def clean_markdown(md: str) -> str:
    md = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    md = _WS_RE.sub(" ", md)
    md = _MULTI_NL_RE.sub("\n\n", md)
    return md.strip()


# 页面尾部常见的服务端诊断/缓存报告（维基百科的 NewPP limit report 等）。
# 它们不是正文，但会被正文抽取器当作内容保留，进而污染关键词、摘要与双链。
_BOILERPLATE_TAIL_RE = re.compile(
    r"\n\s*(?:NewPP limit report"
    r"|Parsed by mw[‐\-]"
    r"|Saved in parser cache with key"
    r"|Rendering was triggered because:"
    r"|Parsoid \d)",
    re.I,
)


def strip_page_boilerplate(md: str) -> str:
    """砍掉正文末尾的解析器诊断块。

    这类块只出现在页面最末，一旦命中，其后全部是服务端调试信息。
    """
    text = md or ""
    match = _BOILERPLATE_TAIL_RE.search(text)
    if not match:
        return text
    return text[: match.start()].rstrip()


def strip_markdown(md: str) -> str:
    """去掉 Markdown 标记，得到纯文本（用于摘要与检索）。

    注意：这里**不压缩空行**。段落边界是后续按空行切段（`compiler._paragraphs`）
    的唯一依据，一旦把 `\\n{2,}` 压成 `\\n`，切段就退化成「一整坨」。
    需要单行文本时由调用方自行 `re.sub(r"\\s+", " ", ...)`。
    """
    text = md or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.M)
    # 强调标记只处理「成对、且位于词边界」的形式。
    # 不能用 re.sub(r"(\*\*|__|\*|_|~~)", "", text) 一把梭 —— 那会把 URL 里的下划线
    # （Retrieval-augmented_generation）和 snake_case 标识符（api_key、max_source_chars）
    # 一起吃掉，留下「Retrieval-augmentedgeneration」这种被压扁的词。
    text = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"\1", text, flags=re.S)
    text = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"\1", text, flags=re.S)
    text = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"\1", text, flags=re.S)
    text = re.sub(r"(?<!\w)\*(?=\S)(.+?)(?<=\S)\*(?!\w)", r"\1", text, flags=re.S)
    text = re.sub(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", r"\1", text, flags=re.S)
    text = re.sub(r"^\s*\|.*\|\s*$", " ", text, flags=re.M)
    text = re.sub(r"^\s*[-:|\s]+$", " ", text, flags=re.M)
    return text.strip()


_CLIP_SEPS = ("。", "！", "？", "；", "，", ".", "!", "?", ";", ",", " ")


def clip(text: str, limit: int) -> str:
    """按长度截断，尽量落在词/句边界上。

    直接 `text[:limit]` 会切出「…to retrieve and incorporat」这种半截词，
    摘要与索引里尤其显眼。这里取 limit 内最靠后的边界；边界太靠前
    （不足 limit 的 60%）就放弃，宁可硬截也不给一个没信息量的短摘要。
    """
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    best = -1
    for sep in _CLIP_SEPS:
        cut = head.rfind(sep)
        if cut > best:
            best = cut
    if best >= limit * 0.6:
        return head[:best].rstrip() + "…"
    return head.rstrip() + "…"


def slugify(title: str, fallback: str = "untitled") -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", (title or "").strip()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug[:60] or fallback).lower()


# --------------------------------------------------------------------------- #
# HTML -> Markdown
# --------------------------------------------------------------------------- #

_DROP_TAGS = {"script", "style", "noscript", "iframe", "svg", "form", "nav", "button", "select", "input"}

# 正文提取时要先干掉的「页面外壳」容器（按 class / id 的单词匹配）
_JUNK_TOKENS = {
    "nav", "navbar", "navigation", "menu", "menubar", "sidebar", "side-bar", "aside",
    "toc", "vector-toc", "table-of-contents", "contents-nav",
    "mw-panel", "mw-portlet", "vector-menu", "vector-tabs", "vector-page-tools",
    "vector-appearance", "vector-user-links", "vector-sticky-header",
    "catlinks", "printfooter", "mw-editsection", "mw-jump-link", "mw-indicators",
    "navbox", "vertical-navbox", "infobox", "metadata", "hatnote", "noprint",
    "reflist", "references", "mw-references-wrap", "shortdescription",
    "footer", "site-footer", "page-footer", "global-footer", "colophon",
    "comment", "comments", "comment-list", "share", "social", "social-share",
    "related", "related-posts", "recommend", "recommendation", "read-more",
    "breadcrumb", "breadcrumbs", "pagination", "pager", "toolbar",
    "advert", "advertisement", "ads", "banner", "promo", "cookie", "consent",
    "popup", "modal", "overlay", "newsletter", "subscribe", "subscription",
    "interlanguage", "language-list", "lang-list", "languages", "mw-interlanguage",
    "skip-link", "screen-reader-text", "visually-hidden", "sr-only",
    "vector-header", "mw-header", "site-header", "page-header", "topbar",
    "vector-column-start", "vector-column-end", "mw-body-header",
}

# 优先尝试的正文容器（命中即用，避免误选）
_CONTENT_SELECTORS = (
    "article", "main", "[role=main]", "[itemprop=articleBody]",
    "#mw-content-text", ".mw-parser-output", "#js_content",
    ".article-content", ".article-body", ".post-content", ".entry-content",
    ".markdown-body", ".rich_media_content", "#content", ".content-body",
)


def _class_tokens(tag: Tag) -> set[str]:
    tokens: set[str] = set()
    for attr in ("class", "id", "role", "data-testid", "aria-label"):
        value = tag.get(attr)
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            tokens.update(str(v).lower() for v in value)
        else:
            tokens.update(str(value).lower().split())
    return tokens


def _prune_chrome(soup: BeautifulSoup) -> None:
    """删掉导航、侧栏、目录、页脚、评论等页面外壳。"""
    for tag in soup(list(_DROP_TAGS)):
        tag.decompose()
    for tag in soup.find_all(True):
        if tag.decomposed:
            continue
        if _class_tokens(tag) & _JUNK_TOKENS:
            tag.decompose()


def _paragraph_score(node: Tag) -> float:
    """用「真实段落」的文本量打分，而不是整块文本量 —— 避免选中导航列表。"""
    paragraphs = node.find_all("p")
    if not paragraphs:
        return 0.0
    p_len = 0
    p_count = 0
    for p in paragraphs:
        length = len(p.get_text(" ", strip=True))
        if length >= 40:
            p_len += length
            p_count += 1
    if p_count == 0:
        return 0.0
    total = len(node.get_text(" ", strip=True)) or 1
    link_len = sum(len(a.get_text(" ", strip=True)) for a in node.find_all("a"))
    link_density = link_len / total
    if link_density > 0.6:
        return 0.0
    # 段落文字占比越高越像正文
    return p_len * (1 - link_density) * min(1.0, p_len / total * 2.2)


def _strip_link_farms(markdown: str) -> str:
    """删掉连续多条的超短列表项（典型的多语言切换、菜单、标签云）。"""
    lines = markdown.split("\n")
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        avg = sum(len(item) for item in run) / len(run)
        if len(run) >= 5 and avg < 26:
            return  # 判定为导航型列表，整段丢弃
        out.extend(run)

    for line in lines:
        if re.match(r"^\s*[-*+]\s+\S", line):
            run.append(line)
            continue
        flush()
        run = []
        out.append(line)
    flush()
    return "\n".join(out)


def readability_extract(html: str) -> tuple[str, str]:
    """轻量正文提取，返回 (title, markdown)。trafilatura 不可用或效果差时的兜底。"""
    soup = BeautifulSoup(html, "lxml")
    _prune_chrome(soup)

    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()

    body = soup.body or soup
    target: Tag | None = None

    # 1) 已知正文容器
    best_known, best_known_score = None, 0.0
    for selector in _CONTENT_SELECTORS:
        for node in soup.select(selector):
            score = _paragraph_score(node)
            if score > best_known_score:
                best_known, best_known_score = node, score
    if best_known is not None and best_known_score > 0:
        target = best_known

    # 2) 打分挑最像正文的块
    if target is None:
        best, best_score = None, 0.0
        for node in body.find_all(["article", "main", "div", "section", "td"]):
            score = _paragraph_score(node)
            if score > best_score:
                best, best_score = node, score
        target = best or body

    markdown = _strip_link_farms(clean_markdown(html_to_markdown(target)))
    if len(strip_markdown(markdown)) < 200:
        fallback = _strip_link_farms(clean_markdown(html_to_markdown(body)))
        if len(strip_markdown(fallback)) > len(strip_markdown(markdown)):
            markdown = fallback
    return title, markdown



def _inline_md(node) -> str:
    if isinstance(node, NavigableString):
        return re.sub(r"\s+", " ", str(node))
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    if name in _DROP_TAGS:
        return ""
    inner = "".join(_inline_md(child) for child in node.children)
    if not inner.strip() and name != "img":
        return inner
    if name in ("strong", "b"):
        return f"**{inner.strip()}**"
    if name in ("em", "i"):
        return f"*{inner.strip()}*"
    if name == "code":
        return f"`{inner.strip()}`"
    if name == "a":
        href = (node.get("href") or "").strip()
        text = inner.strip() or href
        if href.startswith(("http://", "https://")):
            return f"[{text}]({href})"
        return text
    if name == "img":
        alt = (node.get("alt") or "").strip()
        src = (node.get("src") or node.get("data-src") or "").strip()
        if src.startswith(("http://", "https://")):
            return f"![{alt}]({src})"
        return ""
    if name == "br":
        return "\n"
    return inner


def html_to_markdown(node) -> str:
    """把一段 HTML 元素转成 Markdown（覆盖常见的块级元素）。"""
    if isinstance(node, str):
        return re.sub(r"\s+", " ", node)
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    if name in _DROP_TAGS:
        return ""
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        level = int(name[1])
        return f"\n{'#' * level} {_inline_md(node).strip()}\n"
    if name == "p":
        text = _inline_md(node).strip()
        return f"\n{text}\n" if text else ""
    if name == "blockquote":
        body = "".join(html_to_markdown(c) for c in node.children).strip()
        return "\n" + "\n".join("> " + line for line in body.split("\n") if line.strip()) + "\n"
    if name == "pre":
        code = node.get_text()
        lang = ""
        cls = " ".join(node.get("class") or [])
        match = re.search(r"language-([\w+-]+)", cls)
        if match:
            lang = match.group(1)
        return f"\n```{lang}\n{code.strip()}\n```\n"
    if name in ("ul", "ol"):
        ordered = name == "ol"
        lines = []
        for index, li in enumerate(node.find_all("li", recursive=False), start=1):
            body = "".join(html_to_markdown(c) for c in li.children).strip()
            body = re.sub(r"\n+", " ", body).strip()
            if not body:
                continue
            prefix = f"{index}. " if ordered else "- "
            lines.append(prefix + body)
        return "\n" + "\n".join(lines) + "\n" if lines else ""
    if name == "table":
        rows = []
        for tr in node.find_all("tr"):
            cells = [re.sub(r"\s+", " ", cell.get_text()).strip() for cell in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        head = rows[0]
        out = ["| " + " | ".join(head) + " |", "| " + " | ".join(["---"] * width) + " |"]
        for row in rows[1:]:
            out.append("| " + " | ".join(row) + " |")
        return "\n" + "\n".join(out) + "\n"
    if name in ("hr",):
        return "\n---\n"
    if name == "br":
        return "\n"
    if name in ("figcaption",):
        text = _inline_md(node).strip()
        return f"\n*{text}*\n" if text else ""
    if name in ("li", "td", "th", "tr"):
        return "".join(html_to_markdown(c) for c in node.children)
    # 其它块级/未知元素：递归
    return "".join(html_to_markdown(c) for c in node.children)


def join_nonempty(parts: Iterable[str], sep: str = "\n\n") -> str:
    return sep.join(p.strip() for p in parts if p and p.strip())
