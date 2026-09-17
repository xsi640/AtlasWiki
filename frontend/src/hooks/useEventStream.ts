import { useEffect, useRef, useState } from "react";
import type { SseEvent } from "../api/types";

/**
 * 后端实际会广播的事件名（见 backend/src/atlaswiki/jobs.py 与 lint/service.py）：
 * - `job.progress` / `job.done` / `job.failed`：任务队列事件，入队时的第一次广播
 *   也走 `job.progress`（status=queued），因此没有独立的 `job.queued`；
 * - `lint.ready`：体检扫描完成后由 LintService 发布。
 * 订阅后端不会发布的事件名只会白挂监听，故此处只保留这四类。
 */
const SUBSCRIBED_EVENTS = ["job.progress", "job.done", "job.failed", "lint.ready"] as const;

/**
 * 订阅 SSE 事件流，自动重连。
 * 重连后调用方应调 `GET /api/compile/current` 恢复快照（ERROR-007）。
 */
export function useEventStream(onEvent: (event: SseEvent) => void) {
  const [connected, setConnected] = useState(false);
  const callbackRef = useRef(onEvent);
  callbackRef.current = onEvent;

  useEffect(() => {
    const es = new EventSource("/api/events");

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    const handler = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as SseEvent;
        callbackRef.current(data);
      } catch {
        // 心跳注释行不是 JSON，忽略
      }
    };

    for (const type of SUBSCRIBED_EVENTS) {
      es.addEventListener(type, handler);
    }

    return () => {
      es.close();
      setConnected(false);
    };
  }, []);

  return { connected };
}
