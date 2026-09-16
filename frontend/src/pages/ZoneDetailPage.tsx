import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { PageSummary } from "../api/types";

const TYPE_LABELS: Record<string, string> = {
  source: "来源",
  concept: "概念",
  entity: "实体",
  analysis: "分析",
};

export function ZoneDetailPage() {
  const { name } = useParams<{ name: string }>();
  const [pages, setPages] = useState<PageSummary[] | null>(null);

  useEffect(() => {
    if (!name) return;
    api
      .get<{ items: PageSummary[]; total: number }>(
        `/zones/${encodeURIComponent(name)}/pages`,
      )
      .then((res) => setPages(res.items))
      .catch(() => setPages([]));
  }, [name]);

  if (!pages) return <div className="page"><p className="empty-state">加载中…</p></div>;

  return (
    <div className="page">
      <header className="page-header">
        <Link to="/zones" className="back-link">← 全部分区</Link>
        <h1>{name}</h1>
        <p className="page-subtitle">{pages.length} 页</p>
      </header>
      {pages.length === 0 ? (
        <p className="empty-state">此分区暂无页面。</p>
      ) : (
        <ul className="card-list">
          {pages.map((p) => (
            <li key={p.name} className="card-item">
              <Link to={`/page/${encodeURIComponent(p.name)}`} className="card-link">
                <span className={`badge badge-${p.type}`}>
                  {TYPE_LABELS[p.type] ?? p.type}
                </span>
                <strong className="card-title">{p.title}</strong>
                <span className="meta-item">
                  出链 {p.link_count} · 入链 {p.backlink_count}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
