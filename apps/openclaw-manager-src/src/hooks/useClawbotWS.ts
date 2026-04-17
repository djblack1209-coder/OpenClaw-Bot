/**
 * WebSocket 统一推送 Hook — 替代多处 setInterval 轮询
 *
 * 设计思路：
 * 1. 全局单例 WebSocket 连接，所有组件共享
 * 2. 组件通过 useClawbotWS(eventType, callback) 订阅特定事件
 * 3. 自动重连（指数退避 1s→2s→4s→8s→16s，上限 30s）
 * 4. 离线时自动降级回轮询（保持向后兼容）
 */

import { useEffect, useRef, useCallback } from 'react';
import { CLAWBOT_WS_URL } from '@/lib/tauri';

// Event types matching backend WSMessageType
export type WSEventType =
  | 'status'
  | 'trade_signal'
  | 'trade_executed'
  | 'risk_alert'
  | 'bot_error'
  | 'social_published'
  | 'autopilot_event'
  | 'memory_updated'
  | 'evolution_proposal'
  | 'synergy_action'
  | 'notification'      // frontend-only: for notification push
  | 'service_change'    // frontend-only: for service status changes
  | 'heartbeat'
  | '*';                // wildcard: receive all events

export interface WSEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

type WSEventHandler = (event: WSEvent) => void;

// ── Singleton WebSocket Manager ──

class ClawbotWSManager {
  private ws: WebSocket | null = null;
  private listeners = new Map<string, Set<WSEventHandler>>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private _connected = false;
  private _refCount = 0;

  get connected() { return this._connected; }

  subscribe(eventType: string, handler: WSEventHandler) {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set());
    }
    this.listeners.get(eventType)!.add(handler);
    this._refCount++;

    // Auto-connect when first subscriber joins
    if (this._refCount === 1) {
      this.connect();
    }
  }

  unsubscribe(eventType: string, handler: WSEventHandler) {
    const handlers = this.listeners.get(eventType);
    if (handlers) {
      handlers.delete(handler);
      if (handlers.size === 0) this.listeners.delete(eventType);
    }
    this._refCount = Math.max(0, this._refCount - 1);

    // Auto-disconnect when no subscribers
    if (this._refCount === 0) {
      this.disconnect();
    }
  }

  private connect() {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    try {
      const token = import.meta.env.VITE_CLAWBOT_API_TOKEN || '';
      const url = token ? `${CLAWBOT_WS_URL}?token=${encodeURIComponent(token)}` : CLAWBOT_WS_URL;

      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this._connected = true;
        this.reconnectDelay = 1000; // Reset backoff on success
        console.log('[WS] Connected to ClawBot');

        // Start ping interval (every 25s)
        this.pingTimer = setInterval(() => {
          if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send('ping');
          }
        }, 25000);
      };

      this.ws.onmessage = (event) => {
        try {
          if (event.data === 'pong') return; // Ignore pong responses

          const parsed: WSEvent = JSON.parse(event.data);

          // Dispatch to type-specific listeners
          const typeHandlers = this.listeners.get(parsed.type);
          if (typeHandlers) {
            for (const handler of typeHandlers) {
              try { handler(parsed); } catch (err) { console.error('[WS] Handler error:', err); }
            }
          }

          // Dispatch to wildcard listeners
          const wildcardHandlers = this.listeners.get('*');
          if (wildcardHandlers) {
            for (const handler of wildcardHandlers) {
              try { handler(parsed); } catch (err) { console.error('[WS] Handler error:', err); }
            }
          }
        } catch {
          // Ignore unparseable messages
        }
      };

      this.ws.onclose = () => {
        this._connected = false;
        this.cleanupTimers();
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        // Error will trigger onclose, which handles reconnection
      };
    } catch {
      this.scheduleReconnect();
    }
  }

  private disconnect() {
    this.cleanupTimers();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null; // Prevent reconnection
      this.ws.close();
      this.ws = null;
    }
    this._connected = false;
  }

  private cleanupTimers() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private scheduleReconnect() {
    if (this._refCount === 0) return; // Don't reconnect if no subscribers
    if (this.reconnectTimer) return;   // Already scheduled

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectDelay);

    // Exponential backoff
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
  }
}

// Global singleton instance
const wsManager = new ClawbotWSManager();

/**
 * Hook to subscribe to WebSocket events from ClawBot
 *
 * @param eventType - The event type to listen for, or '*' for all events
 * @param handler - Callback invoked with the event data
 *
 * @example
 * ```tsx
 * useClawbotWS('status', (event) => {
 *   setSystemStatus(event.data);
 * });
 * ```
 */
export function useClawbotWS(eventType: WSEventType, handler: WSEventHandler) {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  const stableHandler = useCallback((event: WSEvent) => {
    handlerRef.current(event);
  }, []);

  useEffect(() => {
    wsManager.subscribe(eventType, stableHandler);
    return () => {
      wsManager.unsubscribe(eventType, stableHandler);
    };
  }, [eventType, stableHandler]);
}

/**
 * Hook to get the WebSocket connection status.
 * NOTE: This is a non-reactive read — it returns the value at render time
 * and will NOT trigger re-renders when connection state changes.
 * For reactive connection status, use useClawbotWS('heartbeat', handler).
 */
export function useWSConnectionStatus(): boolean {
  // This is a simplified version - in production you'd use useSyncExternalStore
  return wsManager.connected;
}

// Export manager for direct access in non-React contexts
export { wsManager };
