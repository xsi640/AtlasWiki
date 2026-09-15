import { useEffect, useRef, useState } from "react";
import type { SseEvent } from "../api/types";

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

    for (const type of ["job.queued", "job.progress", "job.done", "job.failed", "lint.ready", "source.status"]) {
      es.addEventListener(type, handler);
    }

    return () => {
      es.close();
      setConnected(false);
    };
  }, []);

  return { connected };
}
