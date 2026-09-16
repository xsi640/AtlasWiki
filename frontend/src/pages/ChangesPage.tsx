import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { ChangeItem, ChangeType, ChangesResponse } from "../api/types";

const CHANGE_LABEL: Record<ChangeType, string> = {
  created: "新建",
  updated: "更新",
  zone_changed: "分区变更",
};

const summaryCard: React.CSSProperties = {
  padding: "var(--sp-5)",
};

const changeRow: React.CSSProperties = {
  display: "block",
  color: "inherit",
  textDecoration: "none",
  padding: "var(--sp-4) var(--sp-5)",
  borderBottom: "1px solid var(--border)",
};

function formatCost(total: number): string {
  return `$${total.toFixed(4)}`;
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string | null {
  if (!startedAt || !finishedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = new Date(finishedAt).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;

  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

function changeBadgeClass(type: ChangeType): string {
  if (type === "created") return "badge badge-success";
  if (type === "zone_changed") return "badge badge-warning";
  return "badge badge-primary";
}

function zoneText(item: ChangeItem): string {
  return item.zone_before ? `${item.zone_before} → ${item.zone}` : item.zone;
}

export function ChangesPage() {
  const [searchParams] = useSearchParams();
  const [changes, setChanges] = useState<ChangesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const jobId = searchParams.get("job_id");

  const loadChanges = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const query = jobId ? `?job_id=${encodeURIComponent(jobId)}` : "";
      const data = await api.get<ChangesResponse>(`/changes${query}`);
      setChanges(data);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "加载变更清单失败");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void loadChanges();
  }, [loadChanges]);

  const items = changes?.items ?? [];
  const failedSources = changes?.failed_sources ?? [];
  const createdCount = items.filter((item) => item.change_type === "created").length;
  const updatedCount = items.filter((item) => item.change_type === "updated").length;
  const zoneChangedCount = items.filter((item) => item.change_type === "zone_changed").length;
  const duration = formatDuration(changes?.started_at ?? null, changes?.finished_at ?? null);

  return (
    <div className="page">
      <h1 className="page-title">这次改动</h1>
      <p className="page-sub">
        {changes
          ? [
              changes.status === "done" ? "编译完成" : changes.status === "failed" ? "编译失败" : "编译已结束",
              duration ? `用时 ${duration}` : null,
              `花费 ${formatCost(changes.cost.total)}`,
            ]
              .filter(Boolean)
              .join(" · ")
          : "查看最近一次编译改了哪些页面。"}
      </p>

      {error && (
        <div className="callout callout-danger" style={{ marginBottom: "var(--sp-4)" }} role="alert">
          {error}
          <div style={{ marginTop: "var(--sp-2)" }}>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void loadChanges()}>
              重试
            </button>
          </div>
        </div>
      )}

      {loading && !changes ? (
        <div className="card card-pad muted">正在加载变更清单…</div>
      ) : items.length === 0 && failedSources.length === 0 ? (
        <div className="card card-pad" style={{ textAlign: "center", padding: "var(--sp-10)" }}>
          <div style={{ fontSize: "var(--fs-h1)", fontWeight: 500 }}>暂无编译变更</div>
          <p className="muted" style={{ margin: "var(--sp-2) 0 0" }}>
            完成一次编译后，新建、更新和分区变化会出现在这里。
          </p>
          <Link to="/ingest" className="btn btn-sm" style={{ display: "inline-flex", marginTop: "var(--sp-4)" }}>
            去投放素材
          </Link>
        </div>
      ) : (
        <>
          <div className="summary" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "var(--sp-4)", marginBottom: "var(--sp-6)" }}>
            <div className="card" style={summaryCard}>
              <div style={{ fontSize: "var(--fs-display)", fontWeight: 500, letterSpacing: "-.5px" }}>{items.length}</div>
              <div className="tiny">改动页面</div>
            </div>
            <div className="card" style={summaryCard}>
              <div style={{ fontSize: "var(--fs-display)", fontWeight: 500, letterSpacing: "-.5px" }}>{createdCount}</div>
              <div className="tiny">新建页面</div>
            </div>
            <div className="card" style={summaryCard}>
              <div style={{ fontSize: "var(--fs-display)", fontWeight: 500, letterSpacing: "-.5px" }}>{updatedCount}</div>
              <div className="tiny">更新页面</div>
            </div>
            <div className="card" style={summaryCard}>
              <div style={{ fontSize: "var(--fs-display)", fontWeight: 500, letterSpacing: "-.5px", color: "var(--warning)" }}>{zoneChangedCount}</div>
              <div className="tiny">分区变更</div>
            </div>
          </div>

          {items.length > 0 && (
            <div className="card">
              <div className="card-head">
                <div className="card-title">改了哪些页面</div>
                <span className="tiny">点击任意一行打开页面</span>
              </div>
              {items.map((item, index) => (
                <Link
                  key={item.name}
                  to={`/page/${encodeURIComponent(item.name)}`}
                  style={{
                    ...changeRow,
                    borderBottom: index === items.length - 1 ? "none" : changeRow.borderBottom,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", minWidth: 0 }}>
                    <span className={changeBadgeClass(item.change_type)}>{CHANGE_LABEL[item.change_type]}</span>
                    <span className="row-title">{item.title}</span>
                    <span className="tag mono">{item.name}</span>
                    {item.has_diff && <span className="tiny">含 diff</span>}
                    <span className="row-meta nowrap">{zoneText(item)}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}

          {failedSources.length > 0 && (
            <>
              <div className="section-label">失败素材</div>
              <div className="card">
                {failedSources.map((source, index) => (
                  <div
                    key={source.id}
                    className="list-row"
                    style={{ alignItems: "flex-start", borderBottom: index === failedSources.length - 1 ? "none" : "1px solid var(--border)" }}
                  >
                    <span className="badge badge-danger">失败</span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="row-title">{source.title}</div>
                      <div className="tiny" style={{ overflowWrap: "anywhere" }}>{source.reason}</div>
                    </div>
                    <Link to={`/sources/${encodeURIComponent(source.id)}`} className="btn btn-ghost btn-sm nowrap">
                      查看素材
                    </Link>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="section-label">本次消耗</div>
          <div className="card card-pad">
            <div style={{ fontSize: "var(--fs-h1)", fontWeight: 500 }}>{formatCost(changes?.cost.total ?? 0)}</div>
            <div className="tiny">
              任务 {changes?.job_id || "—"} · {changes?.cost.currency ?? "USD"}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
