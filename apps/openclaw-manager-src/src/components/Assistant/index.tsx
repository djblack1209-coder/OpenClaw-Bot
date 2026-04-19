import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send,
  Bot,
  User,
  Mic,
  Paperclip,
  MessageSquare,
  Clock,
  Cpu,
  Zap,
  Brain,
  TrendingUp,
  Shield,
  BarChart3,
  Target,
  ScanSearch,
  PenTool,
  Sparkles,
  BookOpen,
  Palette,
  History,
  Plus,
  Trash2,
  Loader2,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import { api } from '../../lib/api';
import { clawbotFetch } from '../../lib/tauri-core';

/* ========== 类型定义 ========== */

/** 助手模式 */
type AssistantMode = 'chat' | 'invest' | 'execute' | 'create';

/** 单条消息 */
interface ChatMessage {
  id: string;
  role: 'user' | 'ai';
  content: string;
  timestamp: string;
}

/** 后端返回的会话概要 */
interface SessionRecord {
  session_id: string;
  title: string;
  created_at: string;
  message_count: number;
  last_message?: string;
}

/* ========== 模式配置 ========== */

/** 每种模式的配色、图标、快捷指令 */
const MODE_CONFIG: Record<
  AssistantMode,
  {
    label: string;
    color: string;
    colorHex: string;
    /** 快捷指令 — 点击后文字会拼接到输入框 */
    commands: { label: string; prefix: string; icon: React.ReactNode }[];
  }
> = {
  chat: {
    label: '闲聊',
    color: '--accent-cyan',
    colorHex: '#00d4ff',
    commands: [
      { label: '今日简报', prefix: '今日简报 ', icon: <BookOpen size={14} /> },
      { label: '天气查询', prefix: '天气查询 ', icon: <Sparkles size={14} /> },
      { label: '翻译文本', prefix: '翻译文本: ', icon: <PenTool size={14} /> },
      { label: '写周报', prefix: '帮我写周报 ', icon: <Palette size={14} /> },
      { label: '知识问答', prefix: '知识问答: ', icon: <Brain size={14} /> },
      { label: '日程安排', prefix: '日程安排 ', icon: <Clock size={14} /> },
    ],
  },
  invest: {
    label: '投资',
    color: '--accent-green',
    colorHex: '#00ffaa',
    commands: [
      { label: '分析AAPL', prefix: '分析AAPL ', icon: <TrendingUp size={14} /> },
      { label: '查看持仓', prefix: '查看持仓 ', icon: <BarChart3 size={14} /> },
      { label: '回测策略', prefix: '回测策略 ', icon: <Target size={14} /> },
      { label: '大师投票', prefix: '大师投票 ', icon: <Brain size={14} /> },
      { label: '风控报告', prefix: '风控报告 ', icon: <Shield size={14} /> },
      { label: '市场扫描', prefix: '市场扫描 ', icon: <ScanSearch size={14} /> },
    ],
  },
  execute: {
    label: '执行',
    color: '--accent-amber',
    colorHex: '#fbbf24',
    commands: [
      { label: '发布推文', prefix: '发布推文 ', icon: <Send size={14} /> },
      { label: '批量操作', prefix: '批量操作 ', icon: <Zap size={14} /> },
      { label: '定时任务', prefix: '定时任务 ', icon: <Clock size={14} /> },
      { label: '数据导出', prefix: '数据导出 ', icon: <BarChart3 size={14} /> },
      { label: '系统检查', prefix: '系统检查 ', icon: <Cpu size={14} /> },
      { label: '日志查看', prefix: '查看日志 ', icon: <History size={14} /> },
    ],
  },
  create: {
    label: '创作',
    color: '--accent-purple',
    colorHex: '#a78bfa',
    commands: [
      { label: '写文章', prefix: '帮我写文章: ', icon: <PenTool size={14} /> },
      { label: '生成图片', prefix: '生成图片: ', icon: <Palette size={14} /> },
      { label: '视频脚本', prefix: '视频脚本: ', icon: <Sparkles size={14} /> },
      { label: '营销文案', prefix: '营销文案: ', icon: <BookOpen size={14} /> },
      { label: '代码生成', prefix: '代码生成: ', icon: <Cpu size={14} /> },
      { label: '头脑风暴', prefix: '头脑风暴: ', icon: <Brain size={14} /> },
    ],
  },
};

/* ========== 工具函数 ========== */

/** 格式化时间戳为 HH:MM */
function formatTime(ts?: string): string {
  if (!ts) {
    const now = new Date();
    return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
  }
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  } catch {
    return ts;
  }
}

/** 格式化会话创建时间（用于右侧列表展示） */
function formatSessionTime(ts: string): string {
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / 86400000);
    const time = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
    if (diffDays === 0) return `今天 ${time}`;
    if (diffDays === 1) return `昨天 ${time}`;
    return `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')} ${time}`;
  } catch {
    return ts;
  }
}

/**
 * 解析 SSE 流并逐块回调
 * 格式: data: {"type":"chunk","content":"..."}\n\n
 *       data: {"type":"done"}\n\n
 */
async function readSSEStream(
  response: Response,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
) {
  const body = response.body;
  if (!body) {
    // 没有流式 body，降级为整体读取
    try {
      const text = await response.text();
      onChunk(text);
    } catch (e) {
      onError(String(e));
    }
    onDone();
    return;
  }

  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      // 按双换行分割 SSE 事件
      const parts = buffer.split('\n\n');
      // 最后一段可能不完整，留在 buffer 里
      buffer = parts.pop() || '';

      for (const part of parts) {
        const trimmed = part.trim();
        if (!trimmed) continue;

        // 提取 data: 后面的 JSON
        const dataMatch = trimmed.match(/^data:\s*(.+)$/m);
        if (!dataMatch) continue;

        try {
          const payload = JSON.parse(dataMatch[1]);
          if (payload.type === 'chunk' && payload.content) {
            onChunk(payload.content);
          } else if (payload.type === 'done') {
            onDone();
            return;
          } else if (payload.type === 'error') {
            onError(payload.content || '未知错误');
            return;
          }
        } catch {
          // JSON 解析失败，把原始文本当内容输出
          onChunk(dataMatch[1]);
        }
      }
    }
    // 流结束，处理残余 buffer
    if (buffer.trim()) {
      const dataMatch = buffer.trim().match(/^data:\s*(.+)$/m);
      if (dataMatch) {
        try {
          const payload = JSON.parse(dataMatch[1]);
          if (payload.type === 'chunk' && payload.content) onChunk(payload.content);
        } catch {
          onChunk(dataMatch[1]);
        }
      }
    }
    onDone();
  } catch (e) {
    onError(String(e));
  }
}

/* ========== 组件 ========== */

export function Assistant() {
  /* --- 状态 --- */
  const [mode, setMode] = useState<AssistantMode>('chat');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);       // AI 正在回复
  const [isLoadingSessions, setIsLoadingSessions] = useState(false); // 加载会话列表
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null); // 正在流式输出的消息 ID

  /* 滚动到底部 */
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const cfg = MODE_CONFIG[mode];

  /* --- 加载会话列表 --- */
  const loadSessions = useCallback(async () => {
    setIsLoadingSessions(true);
    try {
      const data = await api.conversationSessions(50);
      const list: SessionRecord[] = data?.sessions || [];
      setSessions(list);
    } catch (e) {
      console.error('加载会话列表失败:', e);
    } finally {
      setIsLoadingSessions(false);
    }
  }, []);

  /* 初次挂载时加载会话列表 */
  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  /* --- 选中会话 → 加载消息 --- */
  const selectSession = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setMessages([]);
    try {
      const data = await api.conversationGet(sessionId);
      const rawMessages: Array<{ role: string; content: string; timestamp?: string }> =
        data?.messages || [];
      setMessages(
        rawMessages.map((m, i) => ({
          id: `${sessionId}-${i}`,
          role: m.role === 'user' ? 'user' : 'ai',
          content: m.content,
          timestamp: formatTime(m.timestamp),
        })),
      );
    } catch (e) {
      console.error('加载会话消息失败:', e);
    }
  }, []);

  /* --- 新建对话 --- */
  const createSession = useCallback(async () => {
    try {
      const data = await api.conversationCreate('新对话');
      const newId = data?.session_id;
      if (newId) {
        setActiveSessionId(newId);
        setMessages([]);
        await loadSessions(); // 刷新列表
      }
    } catch (e) {
      console.error('创建会话失败:', e);
    }
  }, [loadSessions]);

  /* --- 删除对话 --- */
  const deleteSession = useCallback(
    async (sessionId: string, e: React.MouseEvent) => {
      e.stopPropagation(); // 阻止冒泡到选中事件
      try {
        await api.conversationDelete(sessionId);
        // 如果删的是当前会话，清空聊天区
        if (sessionId === activeSessionId) {
          setActiveSessionId(null);
          setMessages([]);
        }
        await loadSessions();
      } catch (err) {
        console.error('删除会话失败:', err);
      }
    },
    [activeSessionId, loadSessions],
  );

  /* --- 发送消息 --- */
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    // 如果没有活跃会话，先自动创建一个
    let sessionId = activeSessionId;
    if (!sessionId) {
      try {
        const data = await api.conversationCreate(text.slice(0, 30));
        sessionId = data?.session_id;
        if (!sessionId) return;
        setActiveSessionId(sessionId);
        loadSessions();
      } catch (e) {
        console.error('自动创建会话失败:', e);
        return;
      }
    }

    const ts = formatTime();
    const userMsgId = `u-${Date.now()}`;
    const aiMsgId = `a-${Date.now()}`;

    // 立即展示用户消息
    setMessages((prev) => [...prev, { id: userMsgId, role: 'user', content: text, timestamp: ts }]);
    setInput('');
    setIsLoading(true);

    // 先占位一条空的 AI 消息，后续流式填充
    setMessages((prev) => [...prev, { id: aiMsgId, role: 'ai', content: '', timestamp: ts }]);
    setStreamingMsgId(aiMsgId);

    try {
      // 发送请求，不设超时（SSE 流式响应）
      const response = await clawbotFetch(
        `/api/v1/conversation/sessions/${sessionId}/send`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text }),
        },
        0, // 不限超时
      );

      if (!response.ok) {
        const errText = await response.text().catch(() => '');
        throw new Error(`HTTP ${response.status}: ${errText || '请求失败'}`);
      }

      // 读取 SSE 流
      await readSSEStream(
        response,
        (chunk) => {
          // 逐块追加到 AI 消息
          setMessages((prev) =>
            prev.map((m) => (m.id === aiMsgId ? { ...m, content: m.content + chunk } : m)),
          );
        },
        () => {
          // 流结束
          setIsLoading(false);
          setStreamingMsgId(null);
          loadSessions(); // 刷新列表以更新 message_count
        },
        (err) => {
          // 流出错，在消息末尾追加错误提示
          setMessages((prev) =>
            prev.map((m) =>
              m.id === aiMsgId
                ? { ...m, content: m.content || `⚠️ 出错了: ${err}` }
                : m,
            ),
          );
          setIsLoading(false);
          setStreamingMsgId(null);
        },
      );
    } catch (e) {
      // 网络级错误
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? { ...m, content: `⚠️ 发送失败: ${e instanceof Error ? e.message : String(e)}` }
            : m,
        ),
      );
      setIsLoading(false);
      setStreamingMsgId(null);
    }
  }, [input, isLoading, activeSessionId, loadSessions]);

  /* ========== 渲染 ========== */
  return (
    <div className="flex h-full gap-4 p-1">
      {/* ====== 左侧主聊天区 ====== */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* 顶部：模式切换 */}
        <div className="flex items-center gap-2 mb-3 flex-shrink-0">
          {(Object.keys(MODE_CONFIG) as AssistantMode[]).map((m) => {
            const c = MODE_CONFIG[m];
            const active = m === mode;
            return (
              <motion.button
                key={m}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => setMode(m)}
                className={clsx(
                  'px-4 py-1.5 rounded-full text-xs font-medium font-display transition-all duration-200',
                  active
                    ? 'text-[var(--bg-base)]'
                    : 'text-[var(--text-secondary)] border border-[var(--glass-border)] hover:border-[var(--glass-border-hover)]',
                )}
                style={
                  active
                    ? { background: c.colorHex, boxShadow: `0 0 16px ${c.colorHex}33` }
                    : undefined
                }
              >
                {c.label}
              </motion.button>
            );
          })}

          {/* 当前模式指示点 */}
          <div className="ml-auto flex items-center gap-1.5">
            <span
              className="inline-block w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ background: cfg.colorHex }}
            />
            <span className="text-[10px] font-mono text-[var(--text-tertiary)]">在线</span>
          </div>
        </div>

        {/* 消息区域 */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto pr-1 space-y-3 scrollbar-thin scrollbar-thumb-white/10"
        >
          {/* 空状态提示 */}
          {messages.length === 0 && !isLoading && (
            <div className="flex flex-col items-center justify-center h-full text-center opacity-40">
              <Bot size={40} className="mb-3 text-[var(--text-tertiary)]" />
              <p className="text-sm text-[var(--text-tertiary)]">
                {activeSessionId ? '暂无消息，发送一条开始对话' : '选择一个会话或新建对话开始'}
              </p>
            </div>
          )}

          <AnimatePresence initial>
            {messages.map((msg, i) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.04, 0.3), duration: 0.3 }}
                className={clsx('flex gap-2.5', msg.role === 'user' ? 'justify-end' : 'justify-start')}
              >
                {/* AI 头像 */}
                {msg.role === 'ai' && (
                  <div
                    className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1"
                    style={{ background: `${cfg.colorHex}18`, border: `1px solid ${cfg.colorHex}30` }}
                  >
                    <Bot size={14} style={{ color: cfg.colorHex }} />
                  </div>
                )}

                {/* 消息气泡 */}
                <div
                  className={clsx(
                    'abyss-card px-4 py-3 max-w-[75%] text-sm leading-relaxed',
                    msg.role === 'user' && 'border-[var(--accent-cyan)]/20',
                  )}
                  style={msg.role === 'user' ? { borderColor: `${cfg.colorHex}30` } : undefined}
                >
                  {/* 消息内容 — 保留换行 */}
                  <div className="whitespace-pre-wrap text-[var(--text-primary)]">
                    {msg.content}
                    {/* 流式输出时显示闪烁光标 */}
                    {msg.id === streamingMsgId && (
                      <span className="inline-block w-1.5 h-4 ml-0.5 bg-current opacity-70 animate-pulse align-text-bottom" />
                    )}
                  </div>
                  {/* 时间戳 */}
                  <div className="mt-1.5 text-[10px] font-mono text-[var(--text-tertiary)] text-right">
                    {msg.timestamp}
                  </div>
                </div>

                {/* 用户头像 */}
                {msg.role === 'user' && (
                  <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1 bg-[var(--accent-cyan)]/10 border border-[var(--accent-cyan)]/20">
                    <User size={14} className="text-[var(--accent-cyan)]" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* AI 正在思考的加载指示器（仅在消息为空时显示，否则靠流式光标） */}
          {isLoading && messages.length > 0 && !streamingMsgId && (
            <div className="flex gap-2.5 justify-start">
              <div
                className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1"
                style={{ background: `${cfg.colorHex}18`, border: `1px solid ${cfg.colorHex}30` }}
              >
                <Loader2 size={14} className="animate-spin" style={{ color: cfg.colorHex }} />
              </div>
              <div className="abyss-card px-4 py-3 text-sm text-[var(--text-tertiary)]">
                思考中...
              </div>
            </div>
          )}
        </div>

        {/* 输入区域 */}
        <div className="flex-shrink-0 mt-3">
          <div
            className={clsx(
              'flex items-center gap-2 rounded-2xl px-4 py-2.5',
              'bg-[var(--bg-card)] border border-[var(--glass-border)]',
              'backdrop-blur-xl transition-all duration-300',
              'focus-within:border-opacity-100',
            )}
            style={{ boxShadow: `0 0 0 0px ${cfg.colorHex}00` }}
            onFocus={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = `${cfg.colorHex}55`;
              (e.currentTarget as HTMLElement).style.boxShadow = `0 0 20px ${cfg.colorHex}15`;
            }}
            onBlur={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = '';
              (e.currentTarget as HTMLElement).style.boxShadow = '';
            }}
          >
            {/* 附件按钮 */}
            <button className="text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors">
              <Paperclip size={16} />
            </button>

            {/* 输入框 */}
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder={isLoading ? 'AI 正在回复...' : '输入消息...'}
              disabled={isLoading}
              className={clsx(
                'flex-1 bg-transparent text-sm text-[var(--text-primary)] font-body',
                'placeholder:text-[var(--text-tertiary)] outline-none',
                'disabled:opacity-50',
              )}
            />

            {/* 语音按钮 */}
            <button className="text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors">
              <Mic size={16} />
            </button>

            {/* 发送按钮 */}
            <motion.button
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="w-8 h-8 rounded-xl flex items-center justify-center transition-colors disabled:opacity-40"
              style={{
                background: input.trim() && !isLoading ? cfg.colorHex : 'rgba(255,255,255,0.06)',
                color: input.trim() && !isLoading ? 'var(--bg-base)' : 'var(--text-tertiary)',
              }}
            >
              {isLoading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </motion.button>
          </div>
        </div>
      </div>

      {/* ====== 右侧面板 ====== */}
      <div className="w-[280px] flex-shrink-0 flex flex-col gap-3 overflow-y-auto">
        {/* 快捷指令 */}
        <div className="abyss-card p-4">
          <h3 className="text-label text-xs font-display mb-3 flex items-center gap-1.5">
            <Zap size={12} style={{ color: cfg.colorHex }} />
            快捷指令
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {cfg.commands.map((cmd) => (
              <motion.button
                key={cmd.label}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => setInput((prev) => cmd.prefix + prev)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-mono',
                  'bg-white/[0.03] border border-[var(--glass-border)]',
                  'hover:border-opacity-100 transition-all duration-200',
                  'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
                )}
                style={{ ['--tw-border-opacity' as string]: 0.5 }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = `${cfg.colorHex}40`;
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = '';
                }}
              >
                {cmd.icon}
                {cmd.label}
              </motion.button>
            ))}
          </div>
        </div>

        {/* 会话历史 */}
        <div className="abyss-card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-label text-xs font-display flex items-center gap-1.5">
              <History size={12} className="text-[var(--text-tertiary)]" />
              会话记录
            </h3>
            {/* 新建对话按钮 */}
            <motion.button
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              onClick={createSession}
              className="w-6 h-6 rounded-lg flex items-center justify-center bg-white/[0.05] hover:bg-white/[0.1] transition-colors"
              title="新建对话"
            >
              <Plus size={12} className="text-[var(--text-secondary)]" />
            </motion.button>
          </div>

          <div className="space-y-1.5">
            {isLoadingSessions && sessions.length === 0 && (
              <div className="flex items-center justify-center py-4">
                <Loader2 size={16} className="animate-spin text-[var(--text-tertiary)]" />
              </div>
            )}

            {!isLoadingSessions && sessions.length === 0 && (
              <div className="text-center py-4 text-[10px] text-[var(--text-tertiary)]">
                暂无会话记录
              </div>
            )}

            {sessions.map((s, i) => (
              <motion.div
                key={s.session_id}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                onClick={() => selectSession(s.session_id)}
                className={clsx(
                  'group flex items-start justify-between gap-2 px-3 py-2.5 rounded-xl cursor-pointer',
                  'hover:bg-white/[0.03] transition-colors duration-200',
                  s.session_id === activeSessionId && 'bg-white/[0.05] border border-white/[0.06]',
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-[var(--text-primary)] truncate">{s.title}</div>
                  <div className="text-[10px] font-mono text-[var(--text-tertiary)] mt-0.5">
                    {formatSessionTime(s.created_at)}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0 mt-0.5">
                  <MessageSquare size={10} className="text-[var(--text-tertiary)]" />
                  <span className="text-[10px] font-mono text-[var(--text-tertiary)]">
                    {s.message_count}
                  </span>
                  {/* 删除按钮 — 悬停时显示 */}
                  <button
                    onClick={(e) => deleteSession(s.session_id, e)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity ml-1 text-[var(--text-tertiary)] hover:text-red-400"
                    title="删除会话"
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* 系统信息 */}
        <div className="abyss-card p-4">
          <h3 className="text-label text-xs font-display mb-3 flex items-center gap-1.5">
            <Cpu size={12} className="text-[var(--text-tertiary)]" />
            系统信息
          </h3>
          <div className="space-y-2.5">
            {[
              { label: '当前模式', value: cfg.label, color: cfg.colorHex },
              { label: '会话数', value: String(sessions.length), color: '#00ffaa' },
              {
                label: '当前消息',
                value: String(messages.length),
                color: '#fbbf24',
              },
              {
                label: '状态',
                value: isLoading ? '回复中...' : '空闲',
                color: isLoading ? '#fbbf24' : '#00ffaa',
              },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between">
                <span className="text-[11px] text-[var(--text-tertiary)]">{item.label}</span>
                <span className="text-xs font-mono font-medium" style={{ color: item.color }}>
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
