import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useEventStream } from "../hooks/useEventStream";
import type { AskResponse, BootstrapResponse, JobSnapshot } from "../api/types";

export function HomePage() {
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobSnapshot | null>(null);

  useEventStream((e) => {
    if (e.event === "job.done" || e.event === "job.failed") {
      api.get<JobSnapshot>("/compile/current").then(setJob).catch(() => {});
    }
  });

  useEffect(() => {
    api.get<BootstrapResponse>("/system/bootstrap").then(setBootstrap).catch(() => {});
    api.get<JobSnapshot>("/compile/current").then(setJob).catch(() => {});
  }, []);

  const doAsk = async () => {
    if (!question.trim() || asking) return;
    setAsking(true);
    setError(null);
    setAnswer(null);
    try {
      const res = await api.post<AskResponse>("/ask", { question: question.trim() });
      setAnswer(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "提问失败");
    } finally {
      setAsking(false);
    }
  };

  if (bootstrap && bootstrap.is_empty) {
    return (
      <div className="page">
        <header className="page-header">
          <h1>LLM Wiki</h1>
          <p className="page-subtitle">先导入素材，让知识开始生长。</p>
        </header>
        <div className="empty-state">
          <p>知识库还是空的。</p>
          <p>
            去<Link to="/ingest">投放素材</Link>开始吧。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      {job && (job.status === "running" || job.status === "queued") && (
        <div className="job-banner">
          <span>编译中… {job.done_sources}/{job.total_sources}</span>
          <Link to="/compile">查看进度</Link>
        </div>
      )}

      <header className="page-header">
        <h1>LLM Wiki</h1>
        <p className="page-subtitle">对着知识库提问，跨页面综合作答。</p>
      </header>

      <form
        className="ask-bar"
        onSubmit={(e) => { e.preventDefault(); doAsk(); }}
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="输入问题…"
          rows={3}
          className="ask-input"
          aria-label="提问"
          maxLength={500}
        />
        <button type="submit" disabled={!question.trim() || asking} className="btn-primary">
          {asking ? "综合中…" : "提问"}
        </button>
      </form>

      {asking && <p className="empty-state">正在综合知识库页面…</p>}
      {error && <p className="text-danger">{error}</p>}

      {answer && (
        <section className="answer-section">
          {!answer.sufficient ? (
            <div className="empty-state">
              <p>知识不足以回答这个问题。</p>
              {answer.related_pages.length > 0 && (
                <>
                  <p>以下是相关页面：</p>
                  <ul className="card-list">
                    {answer.related_pages.map((p) => (
                      <li key={p.name}>
                        <Link to={`/page/${encodeURIComponent(p.name)}`}>{p.title}</Link>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          ) : (
            <>
              <p className="answer-meta">
                综合了 {answer.pages_considered} 个页面 · 花费 ${answer.cost.total.toFixed(4)}
              </p>
              <div className="answer-content">{answer.answer}</div>
              {answer.citations.length > 0 && (
                <div className="citations">
                  <h3>引用</h3>
                  <ul className="card-list">
                    {answer.citations.map((c) => (
                      <li key={c.page}>
                        <Link to={`/page/${encodeURIComponent(c.page)}`}>{c.title}</Link>
                        {c.anchor_text && <span className="meta-item"> — {c.anchor_text}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <button
                className="btn-secondary"
                disabled={!!answer.saved_page}
                onClick={async () => {
                  try {
                    await api.post(`/ask/${answer.id}/save-as-page`);
                    setAnswer({ ...answer, saved_page: { name: answer.id, title: answer.question } });
                  } catch { /* ignore */ }
                }}
              >
                {answer.saved_page ? "已归档为页面" : "存为页面"}
              </button>
            </>
          )}
        </section>
      )}
    </div>
  );
}
