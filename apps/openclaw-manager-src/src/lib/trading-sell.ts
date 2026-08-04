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
