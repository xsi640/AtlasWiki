import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useEventStream } from "../hooks/useEventStream";
import type { CostInfo, JobSnapshot, JobStatus, JobStep, SseEvent } from "../api/types";

const STATUS_LABEL: Record<JobStatus, string> = {
  idle: "空闲",
  queued: "排队",
  running: "编译中",
  done: "完成",
  failed: "失败",
};

const STEP_LABEL: Record<JobStep["state"], string> = {
  pending: "待处理",
  running: "进行中",
  done: "已完成",
  failed: "失败",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function nullableText(value: unknown, fallback: string | null = null): string | null {
  return typeof value === "string" ? value : fallback;
}

function finiteNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeCost(value: unknown, fallback?: CostInfo): CostInfo {
  if (!isRecord(value)) return fallback ?? { currency: "USD", total: 0 };
  return {
    currency: text(value.currency, "USD"),
    total: finiteNumber(value.total, fallback?.total ?? 0),
  };
}

function normalizeSource(value: unknown): JobSnapshot["current_source"] {
  if (!isRecord(value)) return null;
  const id = text(value.id);
  const title = text(value.title);
  return id || title ? { id, title } : null;
}

function normalizeStep(value: unknown, index: number): JobStep {
  const item = isRecord(value) ? value : {};
  const state = item.state;
  return {
    name: text(item.name, `步骤 ${index + 1}`),
    state:
      state === "running" || state === "done" || state === "failed" ? state : "pending",
  };
}

/**
 * SSE 只提供 JobSnapshot 的精简载荷。合并旧快照可以避免
 * 缺省字段把界面短暂清空，同时保留服务端明确给出的最新值。
 */
function mergeSnapshot(previous: JobSnapshot | null, payload: unknown): JobSnapshot {
  const value = isRecord(payload) ? payload : {};
  const statusValue = value.status;
  const status: JobStatus =
    statusValue === "queued" ||
    statusValue === "running" ||
    statusValue === "done" ||
    statusValue === "failed"
      ? statusValue
      : previous?.status ?? "idle";

  return {
    job_id: nullableText(value.job_id, previous?.job_id ?? null),
    status,
    kind: text(value.kind, previous?.kind ?? "compile"),
    total_sources: Math.max(0, finiteNumber(value.total_sources, previous?.total_sources ?? 0)),
    done_sources: Math.max(0, finiteNumber(value.done_sources, previous?.done_sources ?? 0)),
    current_source: "current_source" in value
      ? normalizeSource(value.current_source)
      : previous?.current_source ?? null,
    current_page: "current_page" in value ? nullableText(value.current_page) : previous?.current_page ?? null,
    steps: Array.isArray(value.steps)
      ? value.steps.map(normalizeStep)
      : previous?.steps ?? [],
    cost: normalizeCost(value.cost, previous?.cost),
    started_at: "started_at" in value ? nullableText(value.started_at) : previous?.started_at ?? null,
    finished_at: "finished_at" in value ? nullableText(value.finished_at) : previous?.finished_at ?? null,
    failure_reason:
      "failure_reason" in value ? nullableText(value.failure_reason) : previous?.failure_reason ?? null,
    can_leave: typeof value.can_leave === "boolean" ? value.can_leave : previous?.can_leave ?? true,
  };
}

function progressPercent(job: JobSnapshot): number {
  if (job.status === "done") return 100;
  if (job.status === "idle") return 0;
  if (job.total_sources <= 0) return job.status === "running" ? 6 : 0;
  const ratio = job.done_sources / job.total_sources;
  return Math.min(100, Math.max(0, Math.round(ratio * 100)));
}

function formatCost(cost: CostInfo): string {
  return `$${cost.total.toFixed(4)}`;
}

function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date);
}

export function CompilePage() {
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const loadSnapshot = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setError(null);

    try {
      const snapshot = await api.get<JobSnapshot>("/compile/current");
      if (requestIdRef.current === requestId) {
        setJob(mergeSnapshot(null, snapshot));
      }
    } catch (cause) {
      if (requestIdRef.current === requestId) {
        setError(cause instanceof Error ? cause.message : "加载编译状态失败");
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  const { connected } = useEventStream(
    useCallback(
      (event: SseEvent) => {
        if (event.event === "job.progress") {
          setJob((current) => {
            const next = mergeSnapshot(current, event);
            if (current?.job_id && next.job_id && current.job_id !== next.job_id) {
              void loadSnapshot();
            }
            return next;
          });
          return;
        }

        if (event.event === "job.done" || event.event === "job.failed") {
          void loadSnapshot();
        }
      },
      [loadSnapshot],
    ),
  );

  useEffect(() => {
    // EventSource 自动重连成功后，hook 会把 connected 翻回 true。
    // 此时必须拉取权威快照，防止丢失断线期间发生的事件。
    if (connected) void loadSnapshot();
  }, [connected, loadSnapshot]);

  if (loading && !job) {
    return (
      <div className="page">
        <h1>围观编译</h1>
        <p className="muted">正在连接编译服务…</p>
      </div>
    );
  }

  if (!job || job.status === "idle") {
    return (
      <div className="page">
        <h1>围观编译</h1>
        <p className="page-sub">投放素材后会在这里实时展示编译进度。</p>
        <div className="card card-pad" style={{ textAlign: "center", padding: "var(--sp-10)" }}>
          <div style={{ fontSize: "var(--fs-h1)", fontWeight: 500 }}>暂无编译任务</div>
          <p className="muted" style={{ margin: "var(--sp-2) 0 0" }}>
            当前没有排队或正在执行的知识编译。
          </p>
          <Link to="/ingest" className="btn btn-sm" style={{ display: "inline-flex", marginTop: "var(--sp-4)" }}>
            去投放素材
          </Link>
        </div>
      </div>
    );
  }

  const percent = progressPercent(job);
  const isActive = job.status === "queued" || job.status === "running";
  const statusColor = job.status === "failed" ? "var(--danger)" : job.status === "done" ? "var(--success)" : "var(--primary)";
  const statusBackground = job.status === "failed"
    ? "var(--danger-soft)"
    : job.status === "done"
      ? "var(--success-soft)"
      : "var(--primary-soft)";

  return (
    <div className="page">
      <div style={{ display: "flex", alignItems: "baseline", gap: "var(--sp-3)" }}>
        <h1 style={{ margin: 0 }}>围观编译</h1>
        <span
          className="badge"
          style={{
            color: statusColor,
            background: statusBackground,
            borderColor: statusColor,
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--sp-2)",
          }}
        >
          {isActive && <span className="dot" />}
          {STATUS_LABEL[job.status]}
        </span>
        <span className="badge" style={{ marginLeft: "auto" }}>
          {connected ? "实时更新" : "重连中"} · 可离开
        </span>
      </div>
      <p className="page-sub">这份素材正在被写进 wiki。你可以留在这儿围观，也可以先去做别的事。</p>

      {error && (
        <div className="callout callout-danger" style={{ marginBottom: "var(--sp-4)" }} role="alert">
          编译状态加载失败：{error}
        </div>
      )}

      <div className="card card-pad" aria-live="polite">
        <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-4)", marginBottom: "var(--sp-3)" }}>
          <div style={{ minWidth: 0 }}>
            <div className="row-title">{job.current_source?.title ?? "等待分配素材"}</div>
            <div className="tiny mono">
              {job.current_page ? `正在写：${job.current_page}` : "尚未开始写入页面"}
            </div>
          </div>
          <span className="badge badge-primary nowrap">
            {job.done_sources}/{job.total_sources} · {percent}%
          </span>
        </div>

        <div
          className="progress"
          style={{ height: 6, background: "var(--code-bg)", borderRadius: "var(--r-full)", overflow: "hidden" }}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-label="编译进度"
        >
          <i
            style={{
              display: "block",
              width: `${percent}%`,
              height: "100%",
              background: "var(--primary)",
              borderRadius: "var(--r-full)",
              transition: "width .28s ease",
            }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "var(--sp-3)", marginTop: "var(--sp-5)" }}>
          <div className="stat" style={{ padding: "var(--sp-4)", border: "1px solid var(--border)", borderRadius: "var(--r-md)", background: "var(--surface-2)" }}>
            <div style={{ fontSize: "var(--fs-h1)", fontWeight: 500 }}>{formatCost(job.cost)}</div>
            <div className="tiny">累计花费</div>
          </div>
          <div className="stat" style={{ padding: "var(--sp-4)", border: "1px solid var(--border)", borderRadius: "var(--r-md)", background: "var(--surface-2)" }}>
            <div style={{ fontSize: "var(--fs-h1)", fontWeight: 500 }}>{job.done_sources}/{job.total_sources}</div>
            <div className="tiny">素材进度</div>
          </div>
          <div className="stat" style={{ padding: "var(--sp-4)", border: "1px solid var(--border)", borderRadius: "var(--r-md)", background: "var(--surface-2)" }}>
            <div style={{ fontSize: "var(--fs-h1)", fontWeight: 500 }}>{formatTime(job.started_at)}</div>
            <div className="tiny">开始时间</div>
          </div>
        </div>

        <div style={{ marginTop: "var(--sp-6)" }}>
          {(job.steps.length > 0 ? job.steps : [{ name: "等待编译步骤", state: "pending" } as JobStep]).map((step, index) => {
            const stepColor =
              step.state === "done"
                ? "var(--success)"
                : step.state === "running"
                  ? "var(--primary)"
                  : step.state === "failed"
                    ? "var(--danger)"
                    : "var(--text-3)";
            const stepBackground =
              step.state === "done"
                ? "var(--success-soft)"
                : step.state === "running"
                  ? "var(--primary)"
                  : step.state === "failed"
                    ? "var(--danger-soft)"
                    : "transparent";
            const stepText = step.state === "running" ? "var(--primary-text)" : stepColor;

            return (
              <div key={`${step.name}-${index}`} style={{ display: "flex", gap: "var(--sp-4)", padding: "var(--sp-3) 0" }}>
                <span
                  aria-hidden="true"
                  style={{
                    width: 22,
                    height: 22,
                    flex: "0 0 auto",
                    display: "grid",
                    placeItems: "center",
                    borderRadius: "var(--r-full)",
                    border: `1px solid ${step.state === "running" || step.state === "done" ? "transparent" : "var(--border-strong)"}`,
                    background: stepBackground,
                    color: stepText,
                    fontSize: "var(--fs-caption)",
                  }}
                >
                  {step.state === "done" ? "✓" : step.state === "failed" ? "!" : index + 1}
                </span>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: "var(--fs-sm)", fontWeight: 500 }}>{step.name}</div>
                  <div className="tiny">{STEP_LABEL[step.state]}</div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="divider" />
        <div className="btn-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <span className="tiny">
            {job.status === "failed"
              ? `失败原因：${job.failure_reason ?? "未知错误"}`
              : job.status === "done"
                ? `完成于 ${formatTime(job.finished_at)}`
                : "所有改动会自动保存，离开后编译继续。"}
          </span>
          {(job.status === "done" || job.status === "failed") && (
            <Link to="/changes" className="btn btn-sm">
              查看变更清单
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
