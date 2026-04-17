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
} from 'lucide-react';
import { motion } from 'framer-motion';
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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const currentModeConfig = MODES.find((m) => m.id === currentMode) || MODES[0];

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
        {/* 对话内容 */}
        <div className="flex-1 overflow-y-auto scroll-container p-6 space-y-4">
          {messages.length === 0 ? (
            /* 空状态：欢迎界面 + 快捷命令 */}
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
    </div>
  );
}

/* ========== 思考动画组件 ========== */
function ThinkingIndicator({ statusText }: { statusText: string }) {
  // 翻译技术状态文本为友好文本
  const getFriendlyStatus = (text: string): string => {
    if (text.includes('brain') || text.includes('调用')) return 'AI 正在思考...';
    if (text.includes('工具') || text.includes('tool')) return '正在处理你的请求...';
    // 如果已经是中文，直接返回
    return text;
  };

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

/* ========== 简单 Markdown 渲染器 ========== */
function MarkdownContent({ content }: { content: string }) {
  // 解析 Markdown 为 React 元素
  const parseMarkdown = (text: string): React.ReactNode[] => {
    const lines = text.split('\n');
    const elements: React.ReactNode[] = [];
    let inCodeBlock = false;
    let codeBlockContent: string[] = [];
    let codeBlockLang = '';

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
          // 开始代码块
          codeBlockLang = line.slice(3).trim();
          inCodeBlock = true;
        }
        return;
      }

      if (inCodeBlock) {
        codeBlockContent.push(line);
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

  // 解析行内 Markdown（粗体、斜体、行内代码）
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
      const nextSpecial = remaining.search(/[`*]/);
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
