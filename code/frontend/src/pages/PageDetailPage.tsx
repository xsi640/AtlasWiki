import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiRequestError } from "../api/client";
import type { PageDetail, PageType } from "../api/types";
import { MarkdownRenderer } from "../components/MarkdownRenderer";

const TYPE_LABEL: Record<PageType, string> = {
  source: "来源页",
  concept: "概念页",
  entity: "实体页",
  analysis: "分析页",
};

const SOURCE_TYPE_LABEL: Record<PageDetail["source_type"], string> = {
  compiled: "LLM 编译",
  "query-generated": "问答生成",
  human: "人工创建",
};

function errorCode(error: unknown): string {
  return error instanceof ApiRequestError ? error.code : "UNKNOWN";
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message || "请求失败";
  return error instanceof Error && error.message ? error.message : "请求失败";
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function statusBadgeClass(status: PageDetail["status"]): string {
  return status === "active" ? "badge badge-success" : "badge badge-warning";
}

function linkList(
  names: readonly string[],
  emptyText: string,
): ReactNode {
  if (names.length === 0) {
    return <div className="tiny">{emptyText}</div>;
  }
  return (
    <div className="hint-row" style={{ marginTop: 0 }}>
      {names.map((name) => (
        <Link key={name} to={`/page/${encodeURIComponent(name)}`} className="chip">
          {name}
        </Link>
      ))}
    </div>
  );
}

export function PageDetailPage() {
  const { name = "" } = useParams<{ name: string }>();
  const [page, setPage] = useState<PageDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [zoneEditing, setZoneEditing] = useState(false);
  const [zoneDraft, setZoneDraft] = useState("");
  const [zoneSaving, setZoneSaving] = useState(false);
  const [zoneError, setZoneError] = useState<string | null>(null);

  const requestRef = useRef(0);

  const loadPage = useCallback(async (pageName: string) => {
    if (!pageName) return;
    const requestId = ++requestRef.current;
    setLoading(true);
    setLoadError(null);
    setNotFound(false);

    try {
      const result = await api.get<PageDetail>(`/pages/${encodeURIComponent(pageName)}`);
      if (requestRef.current === requestId) {
        setPage(result);
      }
    } catch (error) {
      if (requestRef.current !== requestId) return;
      if (errorCode(error) === "E_NOT_FOUND") {
        setNotFound(true);
      } else {
        setLoadError(errorMessage(error));
      }
    } finally {
      if (requestRef.current === requestId) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    setPage(null);
    setEditing(false);
    setZoneEditing(false);
    setDraft("");
    setSaveError(null);
    setZoneError(null);
    void loadPage(name);
  }, [loadPage, name]);

  const startEdit = () => {
    if (!page) return;
    setDraft(page.content);
    setEditing(true);
    setSaveError(null);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft("");
    setSaveError(null);
  };

  const saveContent = async () => {
    if (!page || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api.put<PageDetail>(`/pages/${encodeURIComponent(page.name)}`, {
        content: draft,
      });
      setPage(updated);
      setEditing(false);
      setDraft("");
    } catch (error) {
      setSaveError(errorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  const startZoneEdit = () => {
    if (!page) return;
    setZoneDraft(page.zone);
    setZoneEditing(true);
    setZoneError(null);
  };

  const cancelZoneEdit = () => {
    setZoneEditing(false);
    setZoneDraft("");
    setZoneError(null);
  };

  const saveZone = async () => {
    if (!page || zoneSaving) return;
    const zone = zoneDraft.trim();
    if (!zone) {
      setZoneError("分区名称不能为空");
      return;
    }
    setZoneSaving(true);
    setZoneError(null);
    try {
      await api.patch(`/pages/${encodeURIComponent(page.name)}/zone`, { zone });
      setZoneEditing(false);
      setZoneDraft("");
      await loadPage(page.name);
    } catch (error) {
      setZoneError(errorMessage(error));
    } finally {
      setZoneSaving(false);
    }
  };

  if (notFound) {
    return (
      <div className="container">
        <div className="main">
          <div className="card card-pad" style={{ textAlign: "center", padding: "var(--sp-10)" }} role="alert">
            <h1 className="page-title">页面不存在</h1>
            <p className="muted">没有找到「{name}」，它可能已被删除或链接已失效。</p>
            <Link to="/" className="btn btn-sm" style={{ display: "inline-flex", marginTop: "var(--sp-4)" }}>
              返回首页
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="container">
        <div className="main">
          <div className="callout callout-danger" role="alert">
            {loadError}
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void loadPage(name)}>
              重试
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (loading || !page) {
    return (
      <div className="container">
        <div className="main">
          <div className="card card-pad muted">正在加载页面…</div>
        </div>
      </div>
    );
  }

  const wordCount = page.content.replace(/\s+/g, "").length;
  const sourceCount = page.sources.length;

  return (
    <div className="container">
      <div className="main">
        <div className="crumb">
          <Link to={`/zones/${encodeURIComponent(page.zone)}`}>{page.zone}</Link>
          <span>/</span>
          <span>{TYPE_LABEL[page.type]}</span>
          <span>/</span>
          <span>最后更新 {formatDateTime(page.updated_at)}</span>
        </div>

        {page.human_edited && (
          <div className="callout callout-warning" style={{ marginBottom: "var(--sp-4)" }} role="status">
            <strong>人工编辑保护：</strong>这一页由你修改过，后续编译与体检不会自动覆盖当前内容。
          </div>
        )}

        <div className="title-row">
          <h1 className="page-title" style={{ margin: 0 }}>{page.title}</h1>
          <span className="badge badge-primary">{TYPE_LABEL[page.type]}</span>
          <span className="badge">{SOURCE_TYPE_LABEL[page.source_type]}</span>
          {page.human_edited && <span className="badge badge-accent">已由你编辑</span>}
          <span className={statusBadgeClass(page.status)}>{page.status === "active" ? "正常" : "失效"}</span>

          <div className="btn-row" style={{ marginLeft: "auto" }}>
            {editing ? (
              <>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => void saveContent()} disabled={saving}>
                  {saving ? "保存中…" : "保存"}
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={cancelEdit} disabled={saving}>
                  取消
                </button>
              </>
            ) : (
              <>
                <button type="button" className="btn btn-sm" onClick={startEdit}>编辑</button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={startZoneEdit}>改区</button>
              </>
            )}
            <Link to="/history" className="btn btn-ghost btn-sm">变更记录</Link>
          </div>
        </div>

        {zoneEditing ? (
          <div style={{ marginBottom: "var(--sp-5)" }}>
            <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center" }}>
              <input
                autoFocus
                className="input"
                value={zoneDraft}
                onChange={(event) => setZoneDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void saveZone();
                  if (event.key === "Escape") cancelZoneEdit();
                }}
                style={{
                  width: 220,
                  height: 34,
                  padding: "0 10px",
                  borderRadius: "var(--r-sm)",
                  border: "1px solid var(--border)",
                  background: "var(--surface-2)",
                  color: "var(--text)",
                }}
                aria-label="分区名称"
              />
              <button type="button" className="btn btn-primary btn-sm" onClick={() => void saveZone()} disabled={zoneSaving}>
                确认
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={cancelZoneEdit} disabled={zoneSaving}>
                取消
              </button>
            </div>
            {zoneError && <div className="tiny" style={{ color: "var(--danger)", marginTop: "var(--sp-1)" }}>{zoneError}</div>}
          </div>
        ) : (
          <div className="meta-line mono">
            {page.name}.md · {wordCount} 字 · 所属分区 {page.zone} · 由 {sourceCount} 份素材支撑
          </div>
        )}

        {saveError && (
          <div className="callout callout-danger" style={{ marginBottom: "var(--sp-4)" }} role="alert">{saveError}</div>
        )}

        {editing ? (
          <div style={{ maxWidth: 820 }}>
            <textarea
              className="input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              style={{
                width: "100%",
                minHeight: 460,
                padding: "var(--sp-4)",
                lineHeight: 1.7,
                resize: "vertical",
                borderRadius: "var(--r-md)",
                border: "1px solid var(--border)",
                background: "var(--surface)",
                color: "var(--text)",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--fs-sm)",
              }}
              aria-label="Markdown 正文"
            />
          </div>
        ) : (
          <div className="doc prose" style={{ maxWidth: 820 }}>
            <MarkdownRenderer content={page.content} />

            {page.sources.length > 0 && (
              <div className="source-block">
                <div className="section-label" style={{ marginTop: 0 }}>来源</div>
                {page.sources.map((source) => (
                  <Link
                    key={source.id}
                    to={`/sources/${encodeURIComponent(source.id)}`}
                    className="list-row"
                    style={{ paddingLeft: 0, textDecoration: "none", color: "inherit" }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div className="row-title">{source.title}</div>
                      <div className="tiny mono">{source.kind}</div>
                    </div>
                    <span className="row-meta">查看素材 →</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <aside className="rail">
        <section className="card">
          <div className="card-head">
            <div className="card-title">谁引用了我</div>
            <span className="count-pill">{page.backlinks.length}</span>
          </div>
          <div style={{ padding: "var(--sp-3) var(--sp-5)" }}>
            {page.backlinks.length === 0 ? (
              <div className="tiny">还没有页面引用这一页。</div>
            ) : (
              page.backlinks.map((backlink) => (
                <Link
                  key={backlink.name}
                  to={`/page/${encodeURIComponent(backlink.name)}`}
                  className="backlink-row"
                  style={{ display: "block", textDecoration: "none", color: "inherit" }}
                >
                  <div style={{ fontWeight: 500 }}>{backlink.title}</div>
                  <div className="tiny mono">{backlink.name}</div>
                </Link>
              ))
            )}
          </div>
        </section>

        <div className="section-label">我引用了</div>
        <section className="card card-pad">{linkList(page.links, "还没有出链。")}</section>

        <div className="section-label">元数据</div>
        <section className="card card-pad tiny" style={{ lineHeight: 1.9 }}>
          <div>创建时间：{formatDateTime(page.created_at)}</div>
          <div>更新时间：{formatDateTime(page.updated_at)}</div>
          <div>人工编辑：{page.human_edited ? "是" : "否"}</div>
          {page.origin_source && <div>来源页：<span className="mono">{page.origin_source}</span></div>}
        </section>
      </aside>
    </div>
  );
}
