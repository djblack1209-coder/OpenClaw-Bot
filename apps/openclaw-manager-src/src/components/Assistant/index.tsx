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
  Mic,
  Paperclip,
  Copy,
  ThumbsUp,
  ThumbsDown,
  Activity,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import { toast } from 'sonner';
import { useConversationStore, type Message } from '../../stores/conversationStore';
import {
  fetchSessions,
  createSession,
  loadSession,
  deleteSession,
  sendMessage,
} from '../../services/conversationService';

/* ========== 模式定义 ========== */
type AssistantMode = 'chat' | 'invest' | 'execute' | 'create';

interface ModeConfig {
  id: AssistantMode;
  label: string;
  icon: string;
  commands: Array<{ label: string; prompt: string }>;
}

const MODES: ModeConfig[] = [
  {
    id: 'chat',
    label: '闲聊模式',
    icon: '💬',
    commands: [
      { label: '今日简报', prompt: '给我一份今日运营简报' },
      { label: '天气查询', prompt: '今天天气怎么样？' },
      { label: '购物比价', prompt: '帮我比价一下 iPhone 15 Pro' },
      { label: '日程安排', prompt: '看看我今天有什么安排' },
    ],
  },
  {
    id: 'invest',
    label: '投资模式',
    icon: '📊',
    commands: [
      { label: '分析个股', prompt: '分析一下 AAPL 苹果公司的技术面' },
      { label: '查看持仓', prompt: '看看我现在的持仓情况' },
      { label: '策略回测', prompt: '帮我回测一下双均线策略' },
      { label: 'AI投票', prompt: '看看 AI 投票结果' },
    ],
  },
  {
    id: 'execute',
    label: '执行模式',
    icon: '🤖',
    commands: [
      { label: '闲鱼管理', prompt: '看看闲鱼有没有新消息' },
      { label: '社媒发布', prompt: '帮我发一条小红书' },
      { label: '邮件处理', prompt: '处理一下未读邮件' },
      { label: '赏金任务', prompt: '看看有什么赏金任务' },
    ],
  },
  {
    id: 'create',
    label: '创作模式',
    icon: '🎨',
    commands: [
      { label: '写文案', prompt: '帮我写一条小红书种草文案' },
      { label: '生成图片', prompt: '生成一张产品宣传图' },
      { label: '视频脚本', prompt: '写一个 60 秒短视频脚本' },
      { label: '内容策划', prompt: '策划一个内容营销方案' },
    ],
  },
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
  const [currentMode, setCurrentMode] = useState<AssistantMode>('chat');
  const [showStatusPanel, setShowStatusPanel] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  /** 记录用户是否在消息列表底部附近，用于控制自动滚动 */
  const isNearBottomRef = useRef(true);

  const currentModeConfig = MODES.find((m) => m.id === currentMode) || MODES[0];

  /* 初始化：拉取会话列表 */
  useEffect(() => {
    fetchSessions();
  }, []);

  /* 消息变化时自动滚动到底部 — 仅在用户已处于底部附近时触发 */
  useEffect(() => {
    if (isNearBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
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

  /* 语音输入（占位） */
  const handleVoiceInput = () => {
    toast.info('功能开发中');
  };

  /* 附件上传（占位） */
  const handleAttachment = () => {
    toast.info('功能开发中');
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
        {/* Chat header */}
        <div className="flex items-center justify-end px-4 py-2 border-b border-dark-600">
          <button
            onClick={() => setShowStatusPanel(!showStatusPanel)}
            className={clsx(
              'p-2 rounded-lg transition-colors',
              showStatusPanel ? 'bg-[var(--oc-brand)]/20 text-[var(--oc-brand)]' : 'text-gray-400 hover:text-gray-300'
            )}
            title="执行详情"
          >
            <Activity size={16} />
          </button>
        </div>

        {/* 对话内容 */}
        <div
          ref={messagesContainerRef}
          className="flex-1 overflow-y-auto scroll-container p-6 space-y-4"
          onScroll={() => {
            const el = messagesContainerRef.current;
            if (el) {
              // 用户在底部 100px 范围内视为"在底部"
              isNearBottomRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 100;
            }
          }}
        >
          {messages.length === 0 ? (
            /* 空状态：欢迎界面 + 快捷命令 */
            <div className="h-full flex flex-col items-center justify-center">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-[var(--oc-brand)]/20 to-[var(--oc-brand)]/5 flex items-center justify-center mb-6">
                <Bot size={40} className="text-[var(--oc-brand)]" />
              </div>
              <h2 className="text-2xl font-bold text-white mb-2">有什么可以帮你？</h2>
              <p className="text-sm text-gray-400 mb-2 max-w-md text-center">
                你可以用自然语言和我对话，查行情、下单、管理闲鱼、发社媒，什么都能做
              </p>
              <p className="text-xs text-gray-500 mb-10">
                支持 92 个命令 + 66 个中文触发器
              </p>

              {/* 模式切换器 */}
              <div className="flex items-center gap-2 mb-6 p-1 bg-dark-800 rounded-xl border border-dark-600">
                {MODES.map((mode) => (
                  <button
                    key={mode.id}
                    onClick={() => setCurrentMode(mode.id)}
                    className={clsx(
                      'px-4 py-2 rounded-lg text-sm font-medium transition-all',
                      currentMode === mode.id
                        ? 'bg-[var(--oc-brand)] text-white shadow-lg'
                        : 'text-gray-400 hover:text-gray-300'
                    )}
                  >
                    <span className="mr-1.5">{mode.icon}</span>
                    {mode.label}
                  </button>
                ))}
              </div>

              {/* 快捷命令网格 */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 max-w-3xl">
                {currentModeConfig.commands.map((cmd) => (
                  <button
                    key={cmd.label}
                    onClick={() => handleQuickCommand(cmd.prompt)}
                    className="px-4 py-4 rounded-xl bg-dark-700 hover:bg-dark-600 border border-dark-500 hover:border-[var(--oc-brand)]/30 text-left transition-all group"
                  >
                    <p className="text-sm text-white font-medium mb-1 group-hover:text-[var(--oc-brand)] transition-colors">
                      {cmd.label}
                    </p>
                    <p className="text-xs text-gray-500 line-clamp-2">{cmd.prompt}</p>
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
              {/* 思考动画 */}
              {sending && statusText && (
                <ThinkingIndicator statusText={statusText} />
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* 底部输入区 */}
        <div className="border-t border-dark-600 p-4">
          <div className="max-w-3xl mx-auto">
            {/* 模式切换器（消息列表中显示） */}
            {messages.length > 0 && (
              <div className="flex items-center gap-2 mb-3 justify-center">
                {MODES.map((mode) => (
                  <button
                    key={mode.id}
                    onClick={() => setCurrentMode(mode.id)}
                    className={clsx(
                      'px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                      currentMode === mode.id
                        ? 'bg-[var(--oc-brand)] text-white'
                        : 'text-gray-400 hover:text-gray-300 bg-dark-800'
                    )}
                  >
                    <span className="mr-1">{mode.icon}</span>
                    {mode.label}
                  </button>
                ))}
              </div>
            )}

            {/* 输入框 */}
            <div className="flex items-end gap-2 bg-dark-700 rounded-2xl px-4 py-3 border border-dark-500 focus-within:border-[var(--oc-brand)]/50 transition-colors">
              {/* 语音按钮 */}
              <button
                onClick={handleVoiceInput}
                className="p-2 text-gray-400 hover:text-[var(--oc-brand)] transition-colors flex-shrink-0"
                title="语音输入"
              >
                <Mic size={18} />
              </button>

              {/* 附件按钮 */}
              <button
                onClick={handleAttachment}
                className="p-2 text-gray-400 hover:text-[var(--oc-brand)] transition-colors flex-shrink-0"
                title="上传附件"
              >
                <Paperclip size={18} />
              </button>

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
              {currentModeConfig.commands.slice(0, 4).map((cmd) => (
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

      {/* ========== 右侧执行状态面板 ========== */}
      <AnimatePresence>
        {showStatusPanel && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="flex-shrink-0 border-l border-dark-600 bg-dark-800 overflow-hidden"
          >
            <div className="w-[260px] h-full flex flex-col p-4">
              <h3 className="text-sm font-semibold text-white mb-4 flex items-center gap-2">
                <Activity size={14} />
                执行详情
              </h3>

              {/* Current status */}
              {sending && statusText && (
                <div className="mb-4">
                  <div className="text-xs text-gray-400 mb-2">当前状态</div>
                  <div className="flex items-center gap-2 p-2 rounded-lg bg-[var(--oc-brand)]/10">
                    <Loader2 size={12} className="animate-spin text-[var(--oc-brand)]" />
                    <span className="text-xs text-[var(--oc-brand)]">{statusText}</span>
                  </div>
                </div>
              )}

              {/* Model info */}
              <div className="mb-4">
                <div className="text-xs text-gray-400 mb-2">AI 模型</div>
                <div className="text-sm text-white">AI 助手</div>
              </div>

              {/* Session stats */}
              <div className="mb-4">
                <div className="text-xs text-gray-400 mb-2">本次会话</div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-400">消息数</span>
                    <span className="text-white oc-tabular-nums">{messages.length}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-400">总费用</span>
                    <span className="text-white oc-tabular-nums">
                      ${messages
                        .filter(m => m.metadata?.cost_usd)
                        .reduce((sum, m) => sum + (m.metadata?.cost_usd || 0), 0)
                        .toFixed(4)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Recent operations timeline */}
              <div className="flex-1 overflow-y-auto">
                <div className="text-xs text-gray-400 mb-2">操作历史</div>
                <div className="space-y-2">
                  {messages
                    .filter(m => m.role === 'assistant' && m.metadata && !m.metadata.error)
                    .slice(-5)
                    .reverse()
                    .map((m) => (
                      <div key={m.id} className="p-2 rounded-lg bg-white/5 text-xs">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-300 font-medium">
                            {m.metadata?.task_type || 'AI 回复'}
                          </span>
                          {m.metadata?.elapsed && (
                            <span className="text-gray-500 oc-tabular-nums">
                              {m.metadata.elapsed.toFixed(1)}s
                            </span>
                          )}
                        </div>
                        {m.metadata?.cost_usd != null && (
                          <span className="text-gray-500">
                            费用: ${m.metadata.cost_usd.toFixed(4)}
                          </span>
                        )}
                      </div>
                    ))}
                  {messages.filter(m => m.role === 'assistant' && m.metadata).length === 0 && (
                    <div className="text-center py-4 text-gray-600 text-xs">
                      开始对话后会显示操作记录
                    </div>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ========== 日志翻译层 ========== */
const LOG_TRANSLATIONS: Array<[RegExp, string]> = [
  // Browser automation
  [/browser[._-]?use|navigate|browsing/i, '🌐 正在搜索网页...'],
  [/screenshot|capture/i, '📸 正在截取页面...'],

  // Xianyu
  [/xianyu.*connect|闲鱼.*连接/i, '✅ 闲鱼客服已就绪'],
  [/xianyu.*message|闲鱼.*消息/i, '🐟 处理闲鱼消息...'],

  // Trading
  [/auto_trader.*signal|交易信号/i, '📊 收到交易信号...'],
  [/ibkr|broker|券商/i, '🏦 连接券商...'],
  [/backtest|回测/i, '📈 正在回测...'],
  [/technical.*analysis|技术分析/i, '📉 分析技术指标...'],

  // AI/LLM
  [/litellm.*fallback|模型切换/i, '🔄 AI 切换中...'],
  [/self[_-]?heal.*retry|自愈/i, '🔧 自动修复中...'],
  [/token.*usage|TokenUsage/i, '💰 计算费用...'],
  [/claude|gpt|qwen|deepseek|gemini/i, '🤖 AI 分析中...'],
  [/thinking|reasoning|推理/i, '🧠 深度思考中...'],

  // Tools
  [/tavily|search.*web|网页搜索/i, '🔍 搜索网页...'],
  [/jina.*read|读取网页/i, '📄 读取网页内容...'],
  [/comfyui|generate.*image|生成图片/i, '🎨 生成图片...'],
  [/edge.?tts|语音/i, '🔊 生成语音...'],
  [/whisper|speech.*text|语音识别/i, '🎤 识别语音...'],

  // Social
  [/social.*publish|发布/i, '📱 发布内容...'],
  [/xiaohongshu|小红书/i, '📕 小红书操作中...'],
  [/twitter|推特/i, '🐦 Twitter 操作中...'],

  // Memory
  [/mem0|memory.*search|记忆搜索/i, '🧠 搜索记忆...'],
  [/memory.*store|记忆存储/i, '💾 保存到记忆...'],

  // System
  [/brain.*process|大脑处理/i, 'AI 正在思考...'],
  [/调用|calling|invoke/i, '正在处理你的请求...'],
  [/工具|tool/i, '⚡ 使用工具中...'],
  [/完成|done|finish/i, '✨ 即将完成...'],

  // Execution
  [/bounty|赏金/i, '🏆 执行赏金任务...'],
  [/email.*triage|邮件/i, '📧 处理邮件...'],
  [/shopping|购物|比价/i, '🛒 比价中...'],
];

function getFriendlyStatus(text: string): string {
  // If already looks user-friendly (starts with emoji or status symbol), pass through
  if (/^[\u{1F300}-\u{1FAD6}]/u.test(text) || /^[✅❌⚠️🔄]/.test(text)) {
    return text;
  }

  for (const [pattern, friendly] of LOG_TRANSLATIONS) {
    if (pattern.test(text)) {
      return friendly;
    }
  }

  // Default: if it contains Chinese, keep it; otherwise generic
  if (/[\u4e00-\u9fff]/.test(text)) {
    return text;
  }
  return 'AI 正在思考...';
}

/* ========== 思考动画组件 ========== */
function ThinkingIndicator({ statusText }: { statusText: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3 items-start"
    >
      <div className="w-8 h-8 rounded-lg bg-[var(--oc-brand)]/10 flex items-center justify-center flex-shrink-0">
        <Bot size={16} className="text-[var(--oc-brand)]" />
      </div>
      <div className="flex items-center gap-3 px-4 py-3 rounded-2xl rounded-bl-md bg-dark-700 border border-dark-500">
        {/* 波浪动画点 */}
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-2 h-2 rounded-full bg-[var(--oc-brand)]"
              animate={{
                y: [0, -8, 0],
                opacity: [0.5, 1, 0.5],
              }}
              transition={{
                duration: 0.6,
                repeat: Infinity,
                delay: i * 0.15,
                ease: 'easeInOut',
              }}
            />
          ))}
        </div>
        <span className="text-sm text-gray-400">{getFriendlyStatus(statusText)}</span>
      </div>
    </motion.div>
  );
}

/* ========== 消息气泡组件 ========== */
function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  const isError = message.metadata?.error;
  const [showActions, setShowActions] = useState(false);

  /* 复制消息内容 */
  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    toast.success('已复制到剪贴板');
  };

  /* 反馈按钮（占位） */
  const handleFeedback = (type: 'up' | 'down') => {
    toast.info(`感谢反馈！(${type === 'up' ? '👍' : '👎'})`);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={clsx('flex gap-3', isUser ? 'justify-end' : 'justify-start')}
      onMouseEnter={() => !isUser && setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* AI 头像 */}
      {!isUser && (
        <div className="w-8 h-8 rounded-lg bg-[var(--oc-brand)]/10 flex items-center justify-center flex-shrink-0 mt-1">
          <Bot size={16} className="text-[var(--oc-brand)]" />
        </div>
      )}

      {/* 消息内容 */}
      <div className="flex flex-col gap-2 max-w-[70%]">
        <div
          className={clsx(
            'rounded-2xl px-4 py-3 text-sm leading-relaxed',
            isUser
              ? 'bg-[var(--oc-brand)] text-white rounded-br-md'
              : isError
                ? 'bg-red-500/10 border border-red-500/20 text-red-300 rounded-bl-md'
                : 'bg-dark-700 text-gray-200 border border-dark-500 rounded-bl-md'
          )}
        >
          {/* 渲染 Markdown 内容 */}
          <MarkdownContent content={message.content} />
          {message.streaming && (
            <span className="inline-block w-1.5 h-4 bg-[var(--oc-brand)] rounded-sm ml-0.5 animate-pulse" />
          )}
        </div>

        {/* AI 消息的操作按钮 */}
        {!isUser && !isError && !message.streaming && (
          <motion.div
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: showActions ? 1 : 0, y: showActions ? 0 : -5 }}
            className="flex items-center gap-2 px-2"
          >
            <button
              onClick={handleCopy}
              className="p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-dark-700 transition-colors"
              title="复制"
            >
              <Copy size={14} />
            </button>
            <button
              onClick={() => handleFeedback('up')}
              className="p-1.5 rounded-lg text-gray-500 hover:text-green-400 hover:bg-dark-700 transition-colors"
              title="有帮助"
            >
              <ThumbsUp size={14} />
            </button>
            <button
              onClick={() => handleFeedback('down')}
              className="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-dark-700 transition-colors"
              title="没帮助"
            >
              <ThumbsDown size={14} />
            </button>
            {/* 友好的完成提示 */}
            <span className="text-[10px] text-gray-600 ml-2">AI 分析完成</span>
            {message.metadata?.cost_usd != null && message.metadata.cost_usd > 0 && (
              <span className="text-[10px] text-gray-600 ml-2">
                （费用 ${message.metadata.cost_usd.toFixed(4)}）
              </span>
            )}
          </motion.div>
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

/* ========== 富卡片组件 ========== */
/**
 * 富卡片标记格式（由后端在AI回复中嵌入）:
 * <!--STOCK:AAPL:182.5:+2.3%-->  → 股票行情卡
 * <!--VOTE:BUY:82:AAPL-->        → AI投票结果卡
 * <!--PROGRESS:75:分析市场数据-->  → 进度条卡
 * <!--ALERT:warning:止损预警-->    → 提醒卡
 */

function StockCard({ symbol, price, change }: { symbol: string; price: string; change: string }) {
  const isPositive = !change.startsWith('-');
  return (
    <div className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-dark-800 border border-dark-600 my-1">
      <span className="text-sm font-bold text-white">{symbol}</span>
      <span className="text-sm text-white oc-tabular-nums">${price}</span>
      <span className={clsx('text-xs font-medium oc-tabular-nums', isPositive ? 'text-[var(--oc-success)]' : 'text-[var(--oc-danger)]')}>
        {change}
      </span>
    </div>
  );
}

function VoteCard({ action, confidence, symbol }: { action: string; confidence: string; symbol: string }) {
  const actionColor = action === 'BUY' ? 'text-[var(--oc-success)]' : action === 'SELL' ? 'text-[var(--oc-danger)]' : 'text-[var(--oc-warning)]';
  const actionLabel = action === 'BUY' ? '买入' : action === 'SELL' ? '卖出' : '观望';
  return (
    <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-dark-800 border border-dark-600 my-2">
      <div className="flex items-center gap-2">
        <span className="text-lg">🤖</span>
        <span className="text-sm font-semibold text-white">{symbol}</span>
      </div>
      <div className={clsx('text-sm font-bold', actionColor)}>{actionLabel}</div>
      <div className="flex items-center gap-1">
        <div className="w-16 h-1.5 rounded-full bg-dark-600 overflow-hidden">
          <div className="h-full rounded-full bg-[var(--oc-brand)]" style={{ width: `${confidence}%` }} />
        </div>
        <span className="text-xs text-gray-400">{confidence}%</span>
      </div>
    </div>
  );
}

function ProgressCard({ percent, label }: { percent: string; label: string }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2 rounded-lg bg-dark-800 border border-dark-600 my-1">
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-400">{label}</span>
          <span className="text-xs text-white oc-tabular-nums">{percent}%</span>
        </div>
        <div className="w-full h-1.5 rounded-full bg-dark-600 overflow-hidden">
          <motion.div className="h-full rounded-full bg-[var(--oc-brand)]"
            initial={{ width: 0 }} animate={{ width: `${percent}%` }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          />
        </div>
      </div>
    </div>
  );
}

function AlertCard({ level, message }: { level: string; message: string }) {
  const config = {
    warning: { bg: 'bg-[var(--oc-warning)]/10', border: 'border-[var(--oc-warning)]/30', icon: '⚠️' },
    error: { bg: 'bg-[var(--oc-danger)]/10', border: 'border-[var(--oc-danger)]/30', icon: '🚨' },
    success: { bg: 'bg-[var(--oc-success)]/10', border: 'border-[var(--oc-success)]/30', icon: '✅' },
    info: { bg: 'bg-[var(--oc-brand)]/10', border: 'border-[var(--oc-brand)]/30', icon: 'ℹ️' },
  }[level] || { bg: 'bg-dark-800', border: 'border-dark-600', icon: 'ℹ️' };

  return (
    <div className={clsx('flex items-center gap-2 px-4 py-2 rounded-lg border my-1', config.bg, config.border)}>
      <span>{config.icon}</span>
      <span className="text-sm text-white">{message}</span>
    </div>
  );
}

/* ========== 简单 Markdown 渲染器 ========== */
function MarkdownContent({ content }: { content: string }) {
  // 解析 Markdown 为 React 元素
  const parseMarkdown = (text: string): React.ReactNode[] => {
    const lines = text.split('\n');
    const elements: React.ReactNode[] = [];
    let inCodeBlock = false;
    let codeBlockContent: string[] = [];

    lines.forEach((line, index) => {
      // 代码块开始/结束
      if (line.startsWith('```')) {
        if (inCodeBlock) {
          // 结束代码块
          elements.push(
            <pre key={`code-${index}`} className="bg-dark-900 rounded-lg p-3 my-2 overflow-x-auto">
              <code className="text-xs text-gray-300 font-mono">
                {codeBlockContent.join('\n')}
              </code>
            </pre>
          );
          codeBlockContent = [];
          inCodeBlock = false;
        } else {
          // 开始代码块（忽略语言标记）
          inCodeBlock = true;
        }
        return;
      }

      if (inCodeBlock) {
        codeBlockContent.push(line);
        return;
      }

      // 富卡片标记检测
      const cardMatch = line.match(/<!--(STOCK|VOTE|PROGRESS|ALERT):(.+?)-->/);
      if (cardMatch) {
        const [, type, params] = cardMatch;
        const parts = params.split(':');
        switch (type) {
          case 'STOCK':
            elements.push(<StockCard key={`card-${index}`} symbol={parts[0]} price={parts[1]} change={parts[2]} />);
            break;
          case 'VOTE':
            elements.push(<VoteCard key={`card-${index}`} action={parts[0]} confidence={parts[1]} symbol={parts[2]} />);
            break;
          case 'PROGRESS':
            elements.push(<ProgressCard key={`card-${index}`} percent={parts[0]} label={parts[1]} />);
            break;
          case 'ALERT':
            elements.push(<AlertCard key={`card-${index}`} level={parts[0]} message={parts[1]} />);
            break;
        }
        return;
      }

      // 标题 ###, ##, # (必须先匹配 ### 再 ## 再 #)
      const h3Match = line.match(/^###\s+(.+)/);
      if (h3Match) {
        elements.push(
          <h3 key={`h3-${index}`} className="text-base font-medium text-white mb-1">
            {parseInlineMarkdown(h3Match[1])}
          </h3>
        );
        return;
      }
      const h2Match = line.match(/^##\s+(.+)/);
      if (h2Match) {
        elements.push(
          <h2 key={`h2-${index}`} className="text-lg font-semibold text-white mb-2">
            {parseInlineMarkdown(h2Match[1])}
          </h2>
        );
        return;
      }
      const h1Match = line.match(/^#\s+(.+)/);
      if (h1Match) {
        elements.push(
          <h1 key={`h1-${index}`} className="text-xl font-bold text-white mb-2">
            {parseInlineMarkdown(h1Match[1])}
          </h1>
        );
        return;
      }

      // 列表项
      if (line.match(/^[\-\*\+]\s/)) {
        elements.push(
          <div key={`list-${index}`} className="flex gap-2 my-1">
            <span className="text-gray-500">•</span>
            <span>{parseInlineMarkdown(line.replace(/^[\-\*\+]\s/, ''))}</span>
          </div>
        );
        return;
      }

      // 普通行
      if (line.trim()) {
        elements.push(
          <p key={`line-${index}`} className="my-1">
            {parseInlineMarkdown(line)}
          </p>
        );
      } else {
        elements.push(<br key={`br-${index}`} />);
      }
    });

    return elements;
  };

  // 解析行内 Markdown（粗体、斜体、行内代码、链接）
  const parseInlineMarkdown = (text: string): React.ReactNode => {
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let key = 0;

    while (remaining.length > 0) {
      // 行内代码 `code`
      const codeMatch = remaining.match(/^`([^`]+)`/);
      if (codeMatch) {
        parts.push(
          <code key={key++} className="px-1.5 py-0.5 bg-dark-900 rounded text-[var(--oc-brand)] text-xs font-mono">
            {codeMatch[1]}
          </code>
        );
        remaining = remaining.slice(codeMatch[0].length);
        continue;
      }

      // 链接 [text](url)
      const linkMatch = remaining.match(/^\[([^\]]+)\]\(([^)]+)\)/);
      if (linkMatch) {
        parts.push(
          <a
            key={key++}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--oc-brand)] hover:underline"
          >
            {linkMatch[1]}
          </a>
        );
        remaining = remaining.slice(linkMatch[0].length);
        continue;
      }

      // 粗体 **text**
      const boldMatch = remaining.match(/^\*\*([^*]+)\*\*/);
      if (boldMatch) {
        parts.push(
          <strong key={key++} className="font-bold text-white">
            {boldMatch[1]}
          </strong>
        );
        remaining = remaining.slice(boldMatch[0].length);
        continue;
      }

      // 斜体 *text*
      const italicMatch = remaining.match(/^\*([^*]+)\*/);
      if (italicMatch) {
        parts.push(
          <em key={key++} className="italic">
            {italicMatch[1]}
          </em>
        );
        remaining = remaining.slice(italicMatch[0].length);
        continue;
      }

      // 普通文本
      const nextSpecial = remaining.search(/[`*\[]/);
      if (nextSpecial === -1) {
        parts.push(remaining);
        break;
      } else {
        parts.push(remaining.slice(0, nextSpecial));
        remaining = remaining.slice(nextSpecial);
      }
    }

    return <>{parts}</>;
  };

  return <div className="whitespace-pre-wrap break-words">{parseMarkdown(content)}</div>;
}
