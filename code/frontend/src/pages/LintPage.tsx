import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { LintReport, LintKind } from "../api/types";

const KIND_LABELS: Record<LintKind, string> = {
  contradiction: "矛盾",
  orphan: "孤儿页",
  dead_link: "失效链接",
  missing_index: "缺失索引",
  zone_mix: "分区混杂",
};

export function LintPage() {
  const [report, setReport] = useState<LintReport | null>(null);
  const [running, setRunning] = useState(false);
  const [ignoreReason, setIgnoreReason] = useState<string | null>(null);
  const [pendingIgnore, setPendingIgnore] = useState<string | null>(null);

  const load = () => {
    api.get<LintReport>("/lint/report").then(setReport).catch(() => setReport(null));
  };
  useEffect(load, []);

  const runLint = async () => {
    setRunning(true);
    try {
      await api.post("/lint/run");
      load();
    } catch { /* ignore */ }
    finally { setRunning(false); }
  };

  const ignore = async (issueId: string, reason: string) => {
    if (!reason.trim()) return;
    try {
      await api.post(`/lint/issues/${issueId}/ignore`, { reason: reason.trim() });
      setPendingIgnore(null);
      setIgnoreReason(null);
      load();
    } catch { /* ignore */ }
  };

  const fix = async (issueId: string) => {
    try {
      await api.post(`/lint/issues/${issueId}/fix`);
      load();
    } catch { /* ignore */ }
  };

  if (!report)
    return (
      <div className="page">
        <header className="page-header"><h1>体检</h1></header>
        <p className="empty-state">尚无体检报告。</p>
        <button onClick={runLint} disabled={running} className="btn-primary">
          {running ? "扫描中…" : "开始体检"}
        </button>
      </div>
    );

  const active = report.issues.filter((i) => !i.ignored);
  const ignored = report.issues.filter((i) => i.ignored);
  const groups = new Map<LintKind, typeof active>();
  for (const i of active) {
    const arr = groups.get(i.kind) ?? [];
    arr.push(i);
    groups.set(i.kind, arr);
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>体检</h1>
        <p className="page-subtitle">自动生成但不会自动修复</p>
        <button onClick={runLint} disabled={running} className="btn-primary">
          {running ? "扫描中…" : "重新体检"}
        </button>
      </header>

      {active.length === 0 ? (
        <p className="empty-state">✅ 没有待处理的问题。</p>
      ) : (
        [...groups.entries()].map(([kind, issues]) => (
          <section key={kind}>
            <h2>{KIND_LABELS[kind]} ({issues.length})</h2>
            <ul className="card-list">
              {issues.map((issue) => (
                <li key={issue.id} className="card-item">
                  <div className="card-row">
                    <Link to={`/page/${encodeURIComponent(issue.page)}`}>
                      <strong>{issue.page}</strong>
                    </Link>
                    <span className="meta-item">{issue.detail}</span>
                  </div>
                  <p className="meta-item">建议：{issue.suggestion}</p>
                  <div className="card-row">
                    {issue.repairable && (
                      <button className="btn-secondary" onClick={() => fix(issue.id)}>修复</button>
                    )}
                    <button
                      className="btn-ghost"
                      onClick={() => setPendingIgnore(pendingIgnore === issue.id ? null : issue.id)}
                    >
                      忽略
                    </button>
                  </div>
                  {pendingIgnore === issue.id && (
                    <div className="ignore-form">
                      <input
                        type="text"
                        placeholder="忽略原因（必填）"
                        value={ignoreReason ?? ""}
                        onChange={(e) => setIgnoreReason(e.target.value)}
                      />
                      <button
                        className="btn-primary"
                        onClick={() => ignore(issue.id, ignoreReason ?? "")}
                        disabled={!ignoreReason?.trim()}
                      >
                        确认忽略
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      {ignored.length > 0 && (
        <section>
          <h2>已忽略 ({ignored.length})</h2>
          <ul className="card-list">
            {ignored.map((issue) => (
              <li key={issue.id} className="card-item meta-item">
                {issue.page} — {issue.ignore_reason ?? "无原因"}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
