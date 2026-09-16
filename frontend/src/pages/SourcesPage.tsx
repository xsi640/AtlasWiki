import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { SourceSummary, MaterialStatus } from "../api/types";

const STATUS_LABELS: Record<MaterialStatus, string> = {
  normal: "正常",
  failed: "失败",
  deleted: "已删除",
  stale: "待重编译",
};

const KIND_LABELS: Record<string, string> = {
  web: "网页",
  pdf: "PDF",
  note: "笔记",
};

interface ListResponse {
  items: SourceSummary[];
  total: number;
  counts: Record<string, number>;
}

export function SourcesPage() {
  const [status, setStatus] = useState<MaterialStatus | undefined>(undefined);
  const [data, setData] = useState<ListResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (s?: MaterialStatus) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (s) params.set("status", s);
      const res = await api.get<ListResponse>(`/sources?${params}`);
      setData(res);
    } catch {
      setData({ items: [], total: 0, counts: {} });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(status);
  }, [status, load]);

  return (
    <div className="page">
      <header className="page-header">
        <h1>素材库</h1>
        <p className="page-subtitle">已导入素材与状态一览</p>
      </header>

      <nav className="filter-tabs" aria-label="状态筛选">
        <button
          className={status === undefined ? "tab active" : "tab"}
          onClick={() => setStatus(undefined)}
        >
          全部{data ? ` (${data.total})` : ""}
        </button>
        {(Object.keys(STATUS_LABELS) as MaterialStatus[]).map((s) => (
          <button
            key={s}
            className={status === s ? "tab active" : "tab"}
            onClick={() => setStatus(s)}
          >
            {STATUS_LABELS[s]}
            {data?.counts?.[s] !== undefined ? ` (${data.counts[s]})` : ""}
          </button>
        ))}
      </nav>

      {loading ? (
        <p className="empty-state">加载中…</p>
      ) : !data || data.items.length === 0 ? (
        <p className="empty-state">暂无素材，去投放页添加。</p>
      ) : (
        <ul className="card-list">
          {data.items.map((item) => (
            <li key={item.id} className="card-item">
              <Link to={`/sources/${item.id}`} className="card-link">
                <div className="card-row">
                  <span className={`badge badge-${item.kind}`}>
                    {KIND_LABELS[item.kind] ?? item.kind}
                  </span>
                  <strong className="card-title">{item.title}</strong>
                  <span className={`status-badge status-${item.status}`}>
                    {STATUS_LABELS[item.status]}
                  </span>
                </div>
                <div className="card-row card-meta">
                  {item.source_url && (
                    <span className="meta-item">{item.source_url}</span>
                  )}
                  <span className="meta-item">
                    派生 {item.derived_page_count} 页
                  </span>
                  {item.failure_reason && (
                    <span className="meta-item text-danger">{item.failure_reason}</span>
                  )}
                </div>
                {item.tags.length > 0 && (
                  <div className="card-row">
                    {item.tags.map((t) => (
                      <span key={t} className="tag-chip">{t}</span>
                    ))}
                  </div>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
