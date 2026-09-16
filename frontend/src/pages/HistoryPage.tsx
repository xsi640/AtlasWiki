import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { AskResponse } from "../api/types";

interface QueryListItem {
  id: string;
  question: string;
  sufficient: boolean;
  created_at: string;
  saved_page: { name: string; title: string } | null;
}

export function HistoryPage() {
  const [items, setItems] = useState<QueryListItem[] | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [detail, setDetail] = useState<AskResponse | null>(null);

  const load = () => {
    api
      .get<{ items: QueryListItem[]; total: number }>("/queries")
      .then((res) => setItems(res.items))
      .catch(() => setItems([]));
  };

  useEffect(load, []);

  const toggle = async (id: string) => {
    if (expanded === id) {
      setExpanded(null);
      setDetail(null);
      return;
    }
    setExpanded(id);
    try {
      const res = await api.get<AskResponse>(`/queries/${id}`);
      setDetail(res);
    } catch {
      setDetail(null);
    }
  };

  const remove = async (id: string) => {
    try {
      await api.delete(`/queries/${id}`);
      load();
    } catch {
      /* ignore */
    }
  };

  if (!items) return <div className="page"><p className="empty-state">加载中…</p></div>;
  if (items.length === 0)
    return (
      <div className="page">
        <header className="page-header"><h1>问答历史</h1></header>
        <p className="empty-state">暂无问答记录，去首页提问。</p>
      </div>
    );

  return (
    <div className="page">
      <header className="page-header">
        <h1>问答历史</h1>
        <p className="page-subtitle">{items.length} 条记录</p>
      </header>
      <ul className="card-list">
        {items.map((q) => (
          <li key={q.id} className="card-item">
            <div className="card-row">
              <button
                className="card-link"
                onClick={() => toggle(q.id)}
                style={{ all: "unset", cursor: "pointer", flex: 1 }}
              >
                <strong>{q.question}</strong>
                {q.saved_page && (
                  <span className="badge badge-analysis">已归档</span>
                )}
                <span className="meta-item">{new Date(q.created_at).toLocaleString()}</span>
              </button>
              <button
                className="btn-ghost-danger"
                onClick={(e) => { e.stopPropagation(); remove(q.id); }}
                aria-label="删除"
              >
                删除
              </button>
            </div>
            {expanded === q.id && detail && (
              <div className="query-detail">
                <p className="answer-meta">
                  综合 {detail.pages_considered} 页 · ${detail.cost.total.toFixed(4)}
                </p>
                <div className="answer-content">{detail.answer}</div>
                {detail.saved_page && (
                  <Link to={`/page/${encodeURIComponent(detail.saved_page.name)}`}>
                    查看归档页面 →
                  </Link>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
