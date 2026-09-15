import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { SearchResult } from "../api/types";

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const doSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await api.get<{ items: SearchResult[]; total: number }>(
        `/search?q=${encodeURIComponent(query.trim())}`,
      );
      setResults(res.items);
      setTotal(res.total);
    } catch {
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
      setSearched(true);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1>搜索</h1>
      </header>

      <form
        className="search-bar"
        onSubmit={(e) => {
          e.preventDefault();
          doSearch();
        }}
      >
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索页面标题与正文…"
          className="search-input"
          aria-label="搜索"
        />
        <button
          type="submit"
          disabled={!query.trim() || loading}
          className="btn-primary"
        >
          {loading ? "搜索中…" : "搜索"}
        </button>
      </form>

      {searched && results && (
        <>
          <p className="result-count">
            {total > 0 ? `${total} 条结果` : null}
          </p>
          {results.length === 0 ? (
            <div className="empty-state">
              <p>未找到相关内容。</p>
              <p>
                去<Link to="/ingest">投放素材</Link>或<Link to="/">浏览知识库</Link>。
              </p>
            </div>
          ) : (
            <ul className="card-list">
              {results.map((r) => (
                <li key={r.name} className="card-item">
                  <Link to={`/page/${encodeURIComponent(r.name)}`} className="card-link">
                    <strong className="card-title">{r.title}</strong>
                    <span className={`badge badge-${r.type}`}>{r.type}</span>
                    <span className="meta-item">{r.zone}</span>
                    <p
                      className="search-snippet"
                      dangerouslySetInnerHTML={{ __html: r.snippet }}
                    />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
