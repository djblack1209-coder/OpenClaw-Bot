import { useEffect, useRef, useState } from 'react';
import {
  MessageSquare,
  Plus,
  Send,
  Trash2,
  Loader2,
  Zap,
  Bot,
  User,
} from 'lucide-react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { useConversationStore, type Message } from '../../stores/conversationStore';
import {
  fetchSessions,
  createSession,
  loadSession,
  deleteSession,
  sendMessage,
} from '../../services/conversationService';

/* 快捷命令预设 */
const quickCommands = [
  { label: '今日行情', prompt: '帮我看看今天美股市场情况' },
  { label: '分析个股', prompt: '分析一下 AAPL 苹果公司的技术面' },
  { label: '查看持仓', prompt: '看看我现在的持仓情况' },
  { label: '发布内容', prompt: '帮我写一条小红书种草文案' },
  { label: '闲鱼管理', prompt: '看看闲鱼有没有新消息' },
  { label: '今日简报', prompt: '给我一份今日运营简报' },
];

/**
 * AI 助手 — 完整对话界面
 * 左侧：会话历史列表
 * 右侧：对话窗口 + 输入区
 */
export function Assistant() {
  const sessions = useConversationStore((s) => s.sessions);
  const activeSessionId = useConversationStore((s) => s.activeSessionId);
  const messages = useConversationStore((s) => s.messages);
  const sending = useConversationStore((s) => s.sending);
  const statusText = useConversationStore((s) => s.statusText);
  const loadingSessions = useConversationStore((s) => s.loadingSessions);

  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  /* 初始化：拉取会话列表 */
  useEffect(() => {
    fetchSessions();
  }, []);

  /* 消息变化时自动滚动到底部 */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /* 发送消息 */
  const handleSend = async () => {
    const text = inputValue.trim();
    if (!text || sending) return;

    let sessionId = activeSessionId;

    // 如果没有激活的会话，自动创建一个
    if (!sessionId) {
      sessionId = await createSession();
      if (!sessionId) return;
    }

    setInputValue('');
    await sendMessage(sessionId, text);
    // 刷新会话列表（标题可能更新了）
    fetchSessions();
  };

  /* 键盘快捷键：Enter 发送，Shift+Enter 换行 */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /* 新建对话 */
  const handleNewChat = async () => {
    await createSession();
  };

  /* 点击快捷命令 */
  const handleQuickCommand = (prompt: string) => {
    setInputValue(prompt);
    inputRef.current?.focus();
  };

  return (
    <div className="h-full flex overflow-hidden rounded-xl border border-dark-600">
      {/* ========== 左侧：会话历史 ========== */}
      <div className="w-64 flex-shrink-0 bg-dark-800 border-r border-dark-600 flex flex-col">
        {/* 新建对话按钮 */}
        <div className="p-3 border-b border-dark-600">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--oc-brand)] text-white text-sm font-medium hover:bg-[var(--oc-brand-hover)] transition-colors"
          >
            <Plus size={16} />
            新对话
          </button>
        </div>

        {/* 会话列表 */}
        <div className="flex-1 overflow-y-auto scroll-container p-2 space-y-1">
          {loadingSessions ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={20} className="animate-spin text-gray-500" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-8">
              <MessageSquare size={24} className="mx-auto mb-2 text-gray-600" />
              <p className="text-xs text-gray-500">还没有对话</p>
              <p className="text-xs text-gray-600 mt-1">点击上方按钮开始</p>
            </div>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => loadSession(session.id)}
                className={clsx(
                  'w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all group relative',
                  activeSessionId === session.id
                    ? 'bg-[var(--oc-sidebar-active)] text-white'
                    : 'text-gray-400 hover:bg-dark-700 hover:text-gray-200'
                )}
              >
                <p className="font-medium truncate pr-6">{session.title || '新对话'}</p>
                <p className="text-xs text-gray-500 truncate mt-0.5">
                  {session.message_count}条消息 · {new Date(session.updated_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
                </p>
                {/* 删除按钮 */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(session.id);
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-dark-600 text-gray-500 hover:text-red-400 transition-all"
                >
                  <Trash2 size={14} />
                </button>
              </button>
            ))
          )}
        </div>
      </div>

      {/* ========== 右侧：对话区域 ========== */}
      <div className="flex-1 flex flex-col bg-dark-900">
        {/* 对话内容 */}
        <div className="flex-1 overflow-y-auto scroll-container p-6 space-y-4">
          {messages.length === 0 ? (
            /* 空状态：欢迎界面 + 快捷命令 */
            <div className="h-full flex flex-col items-center justify-center">
              <div className="w-16 h-16 rounded-2xl bg-[var(--oc-brand)]/10 flex items-center justify-center mb-4">
                <Bot size={32} className="text-[var(--oc-brand)]" />
              </div>
              <h2 className="text-xl font-bold text-white mb-2">有什么可以帮你？</h2>
              <p className="text-sm text-gray-400 mb-8 max-w-md text-center">
                你可以用自然语言和我对话，查行情、下单、管理闲鱼、发社媒，什么都能做
              </p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 max-w-xl">
                {quickCommands.map((cmd) => (
                  <button
                    key={cmd.label}
                    onClick={() => handleQuickCommand(cmd.prompt)}
                    className="px-4 py-3 rounded-xl bg-dark-700 hover:bg-dark-600 border border-dark-500 text-left transition-colors"
                  >
                    <p className="text-sm text-white font-medium">{cmd.label}</p>
                    <p className="text-xs text-gray-500 mt-0.5 truncate">{cmd.prompt}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            /* 消息列表 */
            <>
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              {/* 状态提示 */}
              {statusText && (
                <div className="flex items-center gap-2 px-4 py-2">
                  <Loader2 size={14} className="animate-spin text-[var(--oc-brand)]" />
                  <span className="text-xs text-gray-400">{statusText}</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* 底部输入区 */}
        <div className="border-t border-dark-600 p-4">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-end gap-2 bg-dark-700 rounded-2xl px-4 py-3 border border-dark-500 focus-within:border-[var(--oc-brand)]/50 transition-colors">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                rows={1}
                className="flex-1 bg-transparent text-white placeholder-gray-500 outline-none text-sm resize-none max-h-32"
                style={{ minHeight: '24px' }}
                disabled={sending}
              />
              <button
                onClick={handleSend}
                disabled={!inputValue.trim() || sending}
                className={clsx(
                  'p-2 rounded-lg transition-colors flex-shrink-0',
                  inputValue.trim() && !sending
                    ? 'bg-[var(--oc-brand)] text-white hover:bg-[var(--oc-brand-hover)]'
                    : 'text-gray-500 cursor-not-allowed'
                )}
              >
                {sending ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <Send size={18} />
                )}
              </button>
            </div>
            {/* 快捷操作标签 */}
            <div className="flex items-center gap-2 mt-2 justify-center flex-wrap">
              {quickCommands.slice(0, 4).map((cmd) => (
                <button
                  key={cmd.label}
                  onClick={() => handleQuickCommand(cmd.prompt)}
                  className="px-3 py-1 rounded-full bg-dark-700 text-xs text-gray-400 border border-dark-500 hover:border-[var(--oc-brand)]/30 hover:text-gray-300 transition-colors"
                  disabled={sending}
                >
                  <Zap size={10} className="inline mr-1" />
                  {cmd.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ========== 消息气泡组件 ========== */
function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  const isError = message.metadata?.error;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={clsx('flex gap-3', isUser ? 'justify-end' : 'justify-start')}
    >
      {/* AI 头像 */}
      {!isUser && (
        <div className="w-8 h-8 rounded-lg bg-[var(--oc-brand)]/10 flex items-center justify-center flex-shrink-0 mt-1">
          <Bot size={16} className="text-[var(--oc-brand)]" />
        </div>
      )}

      {/* 消息内容 */}
      <div
        className={clsx(
          'max-w-[70%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
          isUser
            ? 'bg-[var(--oc-brand)] text-white rounded-br-md'
            : isError
              ? 'bg-red-500/10 border border-red-500/20 text-red-300 rounded-bl-md'
              : 'bg-dark-700 text-gray-200 border border-dark-500 rounded-bl-md'
        )}
      >
        {/* 文本内容 — 简单支持换行 */}
        <div className="whitespace-pre-wrap break-words">
          {message.content}
          {message.streaming && (
            <span className="inline-block w-1.5 h-4 bg-[var(--oc-brand)] rounded-sm ml-0.5 animate-pulse" />
          )}
        </div>

        {/* 元数据：耗时和成本 */}
        {message.metadata && !message.streaming && message.role === 'assistant' && !isError && (
          <div className="flex items-center gap-3 mt-2 pt-2 border-t border-dark-500/50">
            {message.metadata.elapsed != null && (
              <span className="text-[10px] text-gray-500">
                {message.metadata.elapsed}秒
              </span>
            )}
            {message.metadata.cost_usd != null && message.metadata.cost_usd > 0 && (
              <span className="text-[10px] text-gray-500">
                ${message.metadata.cost_usd.toFixed(4)}
              </span>
            )}
            {message.metadata.task_type && (
              <span className="text-[10px] text-gray-500 px-1.5 py-0.5 bg-dark-600 rounded">
                {message.metadata.task_type}
              </span>
            )}
          </div>
        )}
      </div>

      {/* 用户头像 */}
      {isUser && (
        <div className="w-8 h-8 rounded-lg bg-[var(--oc-brand)]/20 flex items-center justify-center flex-shrink-0 mt-1">
          <User size={16} className="text-[var(--oc-brand)]" />
        </div>
      )}
    </motion.div>
  );
}
