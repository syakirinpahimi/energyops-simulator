// Tiny client-side WebSocket helper. The backend exposes /ws/telemetry?token=...
// For mock mode this returns a fake stream that ticks every second.

import { getToken } from "./auth";
import { isMockEnabled } from "./api.mock";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export interface TelemetryMsg {
  type: "telemetry";
  asset_id: string;
  sensor_id: string;
  metric: string;
  value: number;
  ts: string;
}

export interface StatusMsg {
  type: "status";
  asset_id: string;
  status: "online" | "offline" | "fault" | "maintenance";
  ts: string;
}

export interface AlarmMsg {
  type: "alarm";
  alarm: unknown;
}

export type WsMessage = TelemetryMsg | StatusMsg | AlarmMsg | { type: "ping" | "pong"; ts?: string };

export interface WsHandle {
  close(): void;
}

export function connectTelemetry(
  onMsg: (msg: WsMessage) => void,
  opts: { assetIds?: string[] } = {}
): WsHandle {
  if (isMockEnabled()) return mockWs(onMsg, opts.assetIds ?? []);

  const tok = getToken();
  const url = `${WS_URL}/ws/telemetry${tok ? `?token=${encodeURIComponent(tok)}` : ""}`;
  let ws: WebSocket | null = null;
  let closed = false;
  let backoff = 1000;

  const open = () => {
    if (closed) return;
    ws = new WebSocket(url);
    ws.onopen = () => {
      backoff = 1000;
      if (opts.assetIds?.length) {
        ws?.send(JSON.stringify({ type: "subscribe", asset_ids: opts.assetIds }));
      }
    };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as WsMessage;
        if (msg.type === "ping") ws?.send(JSON.stringify({ type: "pong" }));
        onMsg(msg);
      } catch {
        /* ignore */
      }
    };
    ws.onclose = () => {
      if (closed) return;
      backoff = Math.min(backoff * 2, 30_000);
      setTimeout(open, backoff);
    };
  };

  open();

  return {
    close() {
      closed = true;
      ws?.close();
    }
  };
}

// ---------- mock stream ----------

function mockWs(onMsg: (m: WsMessage) => void, assetIds: string[]): WsHandle {
  const baseAssets = assetIds.length
    ? assetIds
    : ["asset-boiler-2", "asset-pump-p101", "asset-inv-a04", "asset-chiller-1"];
  let stopped = false;

  const tick = () => {
    if (stopped) return;
    for (const id of baseAssets) {
      const t = Date.now();
      const value = +(220 + Math.sin(t / 4000 + id.length) * 18 + Math.random() * 4).toFixed(2);
      onMsg({
        type: "telemetry",
        asset_id: id,
        sensor_id: `${id}-power_kw`,
        metric: "power_kw",
        value,
        ts: new Date().toISOString()
      });
    }
    setTimeout(tick, 1500);
  };

  setTimeout(tick, 250);
  return { close: () => (stopped = true) };
}
