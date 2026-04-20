/**
 * 前端日志工具
 * 统一管理所有前端日志输出，方便调试和追踪
 * 内置脱敏机制：自动检测并掩码 API Key / Token / Cookie / 密码等敏感信息
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/**
 * 敏感信息脱敏规则
 * 匹配常见的 API Key、Token、密码等模式，替换为掩码
 */
const SENSITIVE_PATTERNS: Array<{ pattern: RegExp; replacement: string }> = [
  // Bearer Token: "Bearer sk-xxxx..." → "Bearer sk-****..."
  { pattern: /Bearer\s+[A-Za-z0-9_\-./+=]{8,}/gi, replacement: 'Bearer ****' },
  // API Key 类参数: api_key=xxx / apiKey=xxx / token=xxx
  { pattern: /(api[_-]?key|token|secret|password|authorization|credential|app[_-]?key)[=:]\s*["']?([A-Za-z0-9_\-./+=]{8,})["']?/gi, replacement: '$1=****' },
  // 常见 Key 前缀: sk-xxx / gsk_xxx / xai-xxx / nvapi-xxx / ghp_xxx
  { pattern: /\b(sk-|gsk_|xai-|nvapi-|ghp_|glpat-|Bearer\s+)[A-Za-z0-9_\-./+=]{8,}/gi, replacement: '$1****' },
  // Cookie 字符串: cookie=xxx 或 Cookie: xxx
  { pattern: /(cookie)[=:]\s*["']?[^"'\s]{16,}["']?/gi, replacement: '$1=****' },
  // JSON 格式的敏感字段: "api_key": "xxx" / "token": "xxx" / "password": "xxx"
  { pattern: /"(api[_-]?key|token|secret|password|authorization|cookie|app[_-]?key)"\s*:\s*"([^"]{8,})"/gi, replacement: '"$1":"****"' },
  // 邮箱密码: smtp_password / email_password
  { pattern: /(smtp[_-]?password|email[_-]?password)[=:]\s*["']?[^\s"']{4,}["']?/gi, replacement: '$1=****' },
  // SSH Key / 私钥
  { pattern: /-----BEGIN\s+[A-Z\s]+PRIVATE\s+KEY-----[\s\S]*?-----END\s+[A-Z\s]+PRIVATE\s+KEY-----/g, replacement: '****PRIVATE_KEY****' },
];

/**
 * 对字符串进行敏感信息脱敏
 */
function scrubString(input: string): string {
  let result = input;
  for (const { pattern, replacement } of SENSITIVE_PATTERNS) {
    // 重置 lastIndex（全局正则需要）
    pattern.lastIndex = 0;
    result = result.replace(pattern, replacement);
  }
  return result;
}

/**
 * 递归脱敏：支持字符串、对象、数组
 */
function scrubSecrets(value: unknown): unknown {
  if (typeof value === 'string') {
    return scrubString(value);
  }
  if (Array.isArray(value)) {
    return value.map(scrubSecrets);
  }
  if (value !== null && typeof value === 'object') {
    const scrubbed: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      // 字段名本身就包含敏感关键词的，直接掩码值
      const keyLower = k.toLowerCase();
      if (/(?:api[_-]?key|token|secret|password|authorization|cookie|credential|app[_-]?key)/.test(keyLower)) {
        scrubbed[k] = typeof v === 'string' && v.length > 0 ? '****' : v;
      } else {
        scrubbed[k] = scrubSecrets(v);
      }
    }
    return scrubbed;
  }
  return value;
}

// 日志条目
export interface LogEntry {
  id: number;
  timestamp: Date;
  level: LogLevel;
  module: string;
  message: string;
  args: unknown[];
}

// 日志级别权重
const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

// 日志存储
class LogStore {
  private logs: LogEntry[] = [];
  private maxLogs = 500;
  private idCounter = 0;
  private listeners: Set<() => void> = new Set();

  add(entry: Omit<LogEntry, 'id'>) {
    const newEntry: LogEntry = {
      ...entry,
      id: ++this.idCounter,
    };
    this.logs.push(newEntry);
    
    // 限制日志数量
    if (this.logs.length > this.maxLogs) {
      this.logs = this.logs.slice(-this.maxLogs);
    }
    
    // 通知监听者
    this.listeners.forEach(listener => listener());
  }

  getAll(): LogEntry[] {
    return [...this.logs];
  }

  clear() {
    this.logs = [];
    this.listeners.forEach(listener => listener());
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

// 全局日志存储实例
export const logStore = new LogStore();

// 当前日志级别（可通过 localStorage 设置）
const getCurrentLevel = (): LogLevel => {
  if (typeof window !== 'undefined') {
    const level = localStorage.getItem('LOG_LEVEL') as LogLevel;
    if (level && LOG_LEVELS[level] !== undefined) {
      return level;
    }
  }
  // 默认 debug 级别（开发时显示所有日志）
  return 'debug';
};

// 日志样式
const STYLES: Record<LogLevel, string> = {
  debug: 'color: #888; font-weight: normal',
  info: 'color: #4ade80; font-weight: normal',
  warn: 'color: #facc15; font-weight: bold',
  error: 'color: #f87171; font-weight: bold',
};

// 模块颜色（为不同模块分配不同颜色）
const MODULE_COLORS: Record<string, string> = {
  App: '#a78bfa',
  Service: '#60a5fa',
  Config: '#34d399',
  AI: '#f472b6',
  Channel: '#fb923c',
  Setup: '#22d3ee',
  Dashboard: '#a3e635',
  Testing: '#e879f9',
  API: '#fbbf24',
};

const getModuleColor = (module: string): string => {
  return MODULE_COLORS[module] || '#94a3b8';
};

class Logger {
  private module: string;

  constructor(module: string) {
    this.module = module;
  }

  private shouldLog(level: LogLevel): boolean {
    return LOG_LEVELS[level] >= LOG_LEVELS[getCurrentLevel()];
  }

  private formatMessage(level: LogLevel, message: string, ...args: unknown[]): void {
    if (!this.shouldLog(level)) return;

    const now = new Date();
    const timestamp = now.toLocaleTimeString('zh-CN', { 
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }) + '.' + String(now.getMilliseconds()).padStart(3, '0');
    
    const moduleColor = getModuleColor(this.module);
    const prefix = `%c${timestamp} %c[${this.module}]%c`;
    
    const consoleMethod = level === 'error' ? 'error' : level === 'warn' ? 'warn' : 'log';

    // 脱敏处理：对 message 和 args 中的敏感信息进行掩码
    const safeMessage = scrubString(message);
    const safeArgs = args.map(scrubSecrets);
    
    console[consoleMethod](
      prefix + ` %c${safeMessage}`,
      'color: #666',
      `color: ${moduleColor}; font-weight: bold`,
      '',
      STYLES[level],
      ...safeArgs
    );

    // 存储脱敏后的日志
    logStore.add({
      timestamp: now,
      level,
      module: this.module,
      message: safeMessage,
      args: safeArgs,
    });
  }

  debug(message: string, ...args: unknown[]): void {
    this.formatMessage('debug', message, ...args);
  }

  info(message: string, ...args: unknown[]): void {
    this.formatMessage('info', message, ...args);
  }

  warn(message: string, ...args: unknown[]): void {
    this.formatMessage('warn', message, ...args);
  }

  error(message: string, ...args: unknown[]): void {
    this.formatMessage('error', message, ...args);
  }

  // 记录 API 调用
  apiCall(method: string, ...args: unknown[]): void {
    this.debug(`📡 调用 API: ${method}`, ...args);
  }

  // 记录 API 响应
  apiResponse(method: string, result: unknown): void {
    this.debug(`✅ API 响应: ${method}`, result);
  }

  // 记录 API 错误
  apiError(method: string, error: unknown): void {
    this.error(`❌ API 错误: ${method}`, error);
  }

  // 记录用户操作
  action(action: string, ...args: unknown[]): void {
    this.info(`👆 用户操作: ${action}`, ...args);
  }

  // 记录状态变化
  state(description: string, state: unknown): void {
    this.debug(`📊 状态变化: ${description}`, state);
  }
}

// 导出脱敏函数，供日志导出等场景使用
export { scrubString, scrubSecrets };

// 创建模块 logger 的工厂函数
export function createLogger(module: string): Logger {
  return new Logger(module);
}

// 全局设置日志级别
export function setLogLevel(level: LogLevel): void {
  localStorage.setItem('LOG_LEVEL', level);
  console.log(`%c日志级别已设置为: ${level}`, 'color: #4ade80; font-weight: bold');
}

// 导出预创建的常用 logger
export const appLogger = createLogger('App');
export const serviceLogger = createLogger('Service');
export const configLogger = createLogger('Config');
export const aiLogger = createLogger('AI');
export const channelLogger = createLogger('Channel');
export const setupLogger = createLogger('Setup');
export const dashboardLogger = createLogger('Dashboard');
export const testingLogger = createLogger('Testing');
export const apiLogger = createLogger('API');

// 在控制台暴露日志控制函数
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).setLogLevel = setLogLevel;
  (window as unknown as Record<string, unknown>).logStore = logStore;
  console.log(
    '%c🦞 OpenEverything 日志已启用\n' +
    '%c使用 setLogLevel("debug"|"info"|"warn"|"error") 设置日志级别',
    'color: #a78bfa; font-weight: bold; font-size: 14px',
    'color: #888; font-size: 12px'
  );
}
