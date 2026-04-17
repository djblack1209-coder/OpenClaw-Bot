/**
 * 错误状态友好化 — 将 API/网络错误翻译为用户友好的中文提示
 *
 * 设计原则：
 * 1. 永远不向用户展示原始英文错误或堆栈信息
 * 2. 每条错误消息都附带一个可操作的建议
 * 3. 对常见错误模式做分类匹配
 */

export interface FriendlyError {
  title: string;    // 简短标题
  message: string;  // 详细描述
  suggestion?: string;  // 建议操作
  retryable: boolean;   // 是否可重试
}

// Map HTTP status codes to friendly messages
const HTTP_STATUS_MAP: Record<number, FriendlyError> = {
  400: { title: '请求格式错误', message: '发送的数据格式不正确', suggestion: '请检查输入内容后重试', retryable: false },
  401: { title: '认证失败', message: 'API Token 无效或已过期', suggestion: '请检查设置中的 API Token 配置', retryable: false },
  403: { title: '权限不足', message: '没有执行此操作的权限', suggestion: '请确认账户权限设置', retryable: false },
  404: { title: '资源不存在', message: '请求的数据不存在或已被删除', retryable: false },
  409: { title: '操作冲突', message: '该操作与当前状态冲突', suggestion: '请刷新页面后重试', retryable: true },
  413: { title: '数据过大', message: '发送的数据超过了大小限制', suggestion: '请减少数据量后重试', retryable: false },
  422: { title: '参数验证失败', message: '请检查输入的参数是否正确', retryable: false },
  429: { title: '操作过于频繁', message: '请求频率超过限制', suggestion: '请稍等片刻后再试', retryable: true },
  500: { title: '服务暂时不可用', message: '后端服务遇到问题', suggestion: '请稍后重试，如持续出现请联系支持', retryable: true },
  502: { title: '服务网关错误', message: '无法连接到后端服务', suggestion: '请检查 ClawBot 服务是否启动', retryable: true },
  503: { title: '服务维护中', message: '服务正在维护或重启', suggestion: '请稍等片刻后重试', retryable: true },
};

// Map common error patterns to friendly messages
const ERROR_PATTERN_MAP: Array<{ pattern: RegExp; error: FriendlyError }> = [
  { pattern: /fetch failed|Failed to fetch|NetworkError|network/i, error: { title: '网络连接失败', message: '无法连接到 ClawBot 服务', suggestion: '请检查服务是否启动，或网络是否正常', retryable: true } },
  { pattern: /timeout|ETIMEDOUT|ECONNRESET/i, error: { title: '请求超时', message: '服务响应时间过长', suggestion: '请稍后重试', retryable: true } },
  { pattern: /ECONNREFUSED/i, error: { title: '连接被拒绝', message: 'ClawBot 服务未启动或端口被占用', suggestion: '请前往设置页面启动服务', retryable: true } },
  { pattern: /不在 Tauri 环境/i, error: { title: '环境异常', message: '检测到非 Tauri 环境', suggestion: '请通过 OpenClaw 应用启动', retryable: false } },
  { pattern: /JSON\.parse|Unexpected token|SyntaxError/i, error: { title: '数据解析错误', message: '服务返回了异常数据', suggestion: '请刷新页面后重试', retryable: true } },
  { pattern: /ibkr|IBKR|Interactive Brokers/i, error: { title: 'IBKR 连接问题', message: '无法连接到 Interactive Brokers', suggestion: '请检查 TWS 或 IB Gateway 是否启动', retryable: true } },
  { pattern: /cookie|session|token.*expired/i, error: { title: '登录已过期', message: '会话已失效，需要重新登录', suggestion: '请重新扫码登录', retryable: false } },
];

/**
 * 将任意错误转换为用户友好的中文提示
 */
export function toFriendlyError(error: unknown): FriendlyError {
  // Handle Response objects (from fetch)
  if (error instanceof Response) {
    const mapped = HTTP_STATUS_MAP[error.status];
    if (mapped) return mapped;
    return { title: `服务错误 (${error.status})`, message: '请求未能成功完成', retryable: error.status >= 500 };
  }

  // Handle Error objects
  const message = error instanceof Error ? error.message : String(error || '');

  // Check against pattern map
  for (const { pattern, error: friendlyError } of ERROR_PATTERN_MAP) {
    if (pattern.test(message)) {
      return friendlyError;
    }
  }

  // Default fallback
  return {
    title: '操作失败',
    message: '发生了未知错误',
    suggestion: '请稍后重试，如持续出现请联系支持',
    retryable: true,
  };
}

/**
 * 将错误转换为简短的 toast 消息（用于 sonner toast）
 */
export function toErrorToast(error: unknown): string {
  const friendly = toFriendlyError(error);
  return friendly.suggestion ? `${friendly.title}：${friendly.suggestion}` : friendly.title;
}
