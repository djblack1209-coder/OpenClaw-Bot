export interface TradingSellResponse {
  success: true;
  message?: string;
  order_id?: string | number;
  [key: string]: unknown;
}

/** 只有后端明确确认提交成功时，前端才允许展示卖出成功。 */
export function assertTradingSellSucceeded(payload: unknown): TradingSellResponse {
  const record = payload && typeof payload === 'object'
    ? payload as Record<string, unknown>
    : null;
  if (!record || record.success !== true) {
    const message = record && typeof record.message === 'string'
      ? record.message.trim()
      : '';
    throw new Error(message || '卖出请求失败：后端未确认订单提交');
  }
  return record as TradingSellResponse;
}

export const MANUAL_SELL_PROTOCOL = 'manual-sell-v1';
export const MANUAL_SELL_REFERENCE_KEY = 'openclaw.manualSell.requestId.v1';
const requestIdPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const states = ['prepared', 'claimed', 'dispatched', 'submitted', 'partially_filled', 'filled', 'rejected', 'cancelled', 'expired', 'unknown'] as const;
export type ManualSellState = typeof states[number];
export interface ManualSellStatus {
  request_id: string;
  protocol: typeof MANUAL_SELL_PROTOCOL;
  state: ManualSellState;
  expires_at: number;
  challenge?: string;
  summary: {
    symbol: string; quantity: string; order_type: 'MKT' | 'LMT'; limit_price: string | null;
    account: string; environment: 'paper' | 'live'; broker: 'ibkr'; currency: string;
    con_id: number; broker_protocol: string; server_version: number;
  };
  success: boolean;
  requires_reconciliation: boolean;
  filled_qty?: number;
}
export interface ManualSellConfirmation {
  request_id: string; symbol: string; quantity: number; order_type: 'MKT' | 'LMT'; limit_price: number | null;
  protocol: typeof MANUAL_SELL_PROTOCOL; challenge: string; confirmed: true;
}

export function parseManualSellStatus(value: unknown, requestId: string): ManualSellStatus {
  const result = value as ManualSellStatus | null;
  if (!result || !requestIdPattern.test(requestId) || result.request_id !== requestId
    || result.protocol !== MANUAL_SELL_PROTOCOL || !states.includes(result.state)
    || !Number.isFinite(result.expires_at) || !result.summary
    || !['paper', 'live'].includes(result.summary.environment) || result.summary.broker !== 'ibkr'
    || typeof result.summary.account !== 'string' || !result.summary.account
    || typeof result.summary.symbol !== 'string' || !result.summary.symbol
    || !Number.isFinite(Number(result.summary.quantity)) || Number(result.summary.quantity) <= 0
    || !['MKT', 'LMT'].includes(result.summary.order_type)
    || (result.summary.order_type === 'MKT' && result.summary.limit_price !== null)
    || (result.summary.order_type === 'LMT' && (!Number.isFinite(Number(result.summary.limit_price)) || Number(result.summary.limit_price) <= 0))
    || typeof result.summary.currency !== 'string' || !result.summary.currency
    || result.summary.broker_protocol !== 'tws-api' || !Number.isInteger(result.summary.server_version) || result.summary.server_version <= 0
    || !Number.isInteger(result.summary.con_id) || result.summary.con_id <= 0
    || typeof result.success !== 'boolean' || typeof result.requires_reconciliation !== 'boolean') {
    throw new Error('Invalid manual sell status; query the original request');
  }
  if (result.success !== ['submitted', 'partially_filled', 'filled'].includes(result.state)) {
    throw new Error('Inconsistent manual sell status');
  }
  return result;
}

export function createManualSellConfirmation(status: ManualSellStatus, now = Date.now()): ManualSellConfirmation {
  parseManualSellStatus(status, status.request_id);
  if (status.state !== 'prepared' || typeof status.challenge !== 'string' || status.challenge.length < 20
    || now / 1000 >= status.expires_at) {
    throw new Error('Confirmation expired or unavailable');
  }
  return {
    request_id: status.request_id, protocol: MANUAL_SELL_PROTOCOL, challenge: status.challenge, confirmed: true,
    symbol: status.summary.symbol, quantity: Number(status.summary.quantity), order_type: status.summary.order_type,
    limit_price: status.summary.limit_price === null ? null : Number(status.summary.limit_price),
  };
}

export function isManualSellTerminal(state: ManualSellState): boolean {
  return ['filled', 'rejected', 'cancelled', 'expired'].includes(state);
}

export function readManualSellReference(storage: Pick<Storage, 'getItem'>): string | null {
  const value = storage.getItem(MANUAL_SELL_REFERENCE_KEY);
  if (value === null) return null;
  if (!requestIdPattern.test(value)) throw new Error('Invalid saved order reference');
  return value;
}

export function saveManualSellReference(storage: Pick<Storage, 'setItem' | 'getItem'>, requestId: string): void {
  if (!requestIdPattern.test(requestId)) throw new Error('Invalid order reference');
  storage.setItem(MANUAL_SELL_REFERENCE_KEY, requestId);
  if (readManualSellReference(storage) !== requestId) throw new Error('Order reference could not be saved');
}

export function clearManualSellReference(storage: Pick<Storage, 'getItem' | 'removeItem'>, requestId: string): void {
  if (readManualSellReference(storage) === requestId) storage.removeItem(MANUAL_SELL_REFERENCE_KEY);
}
