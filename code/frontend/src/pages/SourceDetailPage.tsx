import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { SourceDetail } from "../api/types";

export function SourceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .get<SourceDetail>(`/sources/${id}`)
      .then(setSource)
      .catch((e) => setError(e.message ?? "加载失败"));
  }, [id]);

  if (error) return <div className="page"><p className="empty-state">{error}</p></div>;
  if (!source) return <div className="page"><p className="empty-state">加载中…</p></div>;

  return (
    <div className="page">
      <header className="page-header">
        <h1>{source.title}</h1>
        <p className="page-subtitle">
          {source.kind.toUpperCase()} · {source.status}
        </p>
      </header>

      {source.source_url && (
        <p>
          <a href={source.source_url} target="_blank" rel="noopener noreferrer">
            {source.source_url}
          </a>
        </p>
      )}

      {source.author && <p>作者：{source.author}</p>}
      {source.tags.length > 0 && (
        <div className="card-row">
          {source.tags.map((t) => (
            <span key={t} className="tag-chip">{t}</span>
          ))}
        </div>
      )}

      {source.asset_path && (
        <p>
          <a href={`/api/sources/${source.id}/asset?download=1`} download>
            下载原件
          </a>
        </p>
      )}

      <section>
        <h2>正文预览</h2>
        <pre className="source-content">{source.content || "（无正文）"}</pre>
      </section>

      {source.derived_pages.length > 0 && (
        <section>
          <h2>派生页面 ({source.derived_pages.length})</h2>
          <ul className="card-list">
            {source.derived_pages.map((p) => (
              <li key={p.name}>
                <Link to={`/page/${p.name}`}>{p.title}</Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {source.failure_reason && (
        <p className="text-danger">失败原因：{source.failure_reason}</p>
      )}
    </div>
  );
}
