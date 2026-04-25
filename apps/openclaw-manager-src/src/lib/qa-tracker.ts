/**
 * QA 交互追踪器 — 记录用户点击和页面等待时间
 * 数据仅存本地，用于优化用户体验
 */

interface InteractionEvent {
  type: 'click' | 'page_load' | 'api_wait' | 'error';
  target: string;        // 页面名或按钮标识
  duration_ms?: number;  // 等待时间
  timestamp: number;
  metadata?: Record<string, unknown>;
}

// 内存中最多保留的事件数量
const MAX_EVENTS = 500;
const events: InteractionEvent[] = [];

export function trackClick(target: string, metadata?: Record<string, unknown>) {
  pushEvent({ type: 'click', target, timestamp: Date.now(), metadata });
}

export function trackPageLoad(pageName: string, durationMs: number) {
  pushEvent({ type: 'page_load', target: pageName, duration_ms: durationMs, timestamp: Date.now() });
}

export function trackApiWait(endpoint: string, durationMs: number) {
  pushEvent({ type: 'api_wait', target: endpoint, duration_ms: durationMs, timestamp: Date.now() });
}

export function trackError(target: string, error: string) {
  pushEvent({ type: 'error', target, timestamp: Date.now(), metadata: { error } });
}

function pushEvent(event: InteractionEvent) {
  events.push(event);
  if (events.length > MAX_EVENTS) events.shift();
}

// 生成 QA 汇总报告
export function getQAReport() {
  const pageLoads = events.filter(e => e.type === 'page_load');
  const apiWaits = events.filter(e => e.type === 'api_wait');
  const clicks = events.filter(e => e.type === 'click');
  const errors = events.filter(e => e.type === 'error');

  const avgPageLoad = pageLoads.length
    ? pageLoads.reduce((sum, e) => sum + (e.duration_ms || 0), 0) / pageLoads.length
    : 0;
  const avgApiWait = apiWaits.length
    ? apiWaits.reduce((sum, e) => sum + (e.duration_ms || 0), 0) / apiWaits.length
    : 0;
  const slowPages = pageLoads.filter(e => (e.duration_ms || 0) > 3000);
  const slowApis = apiWaits.filter(e => (e.duration_ms || 0) > 5000);

  return {
    total_clicks: clicks.length,
    total_page_loads: pageLoads.length,
    avg_page_load_ms: Math.round(avgPageLoad),
    avg_api_wait_ms: Math.round(avgApiWait),
    slow_pages: slowPages.map(e => ({ page: e.target, ms: e.duration_ms })),
    slow_apis: slowApis.map(e => ({ endpoint: e.target, ms: e.duration_ms })),
    errors: errors.length,
    recent_errors: errors.slice(-5).map(e => ({ target: e.target, error: e.metadata?.error })),
  };
}

// 导出原始事件用于调试
export function getRawEvents() { return [...events]; }
export function clearEvents() { events.length = 0; }
