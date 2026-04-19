import { useState, useRef, useEffect } from 'react';
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
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';

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

/** 会话记录 */
interface SessionRecord {
  id: string;
  title: string;
  time: string;
  count: number;
}

/* ========== 模式配置 ========== */

/** 每种模式的配色、图标、快捷指令 */
const MODE_CONFIG: Record<
  AssistantMode,
  {
    label: string;
    color: string;      // CSS 变量名
    colorHex: string;    // 用于内联样式
    commands: { label: string; icon: React.ReactNode }[];
  }
> = {
  chat: {
    label: '闲聊',
    color: '--accent-cyan',
    colorHex: '#00d4ff',
    commands: [
      { label: '今日简报', icon: <BookOpen size={14} /> },
      { label: '天气查询', icon: <Sparkles size={14} /> },
      { label: '翻译文本', icon: <PenTool size={14} /> },
      { label: '写周报', icon: <Palette size={14} /> },
      { label: '知识问答', icon: <Brain size={14} /> },
      { label: '日程安排', icon: <Clock size={14} /> },
    ],
  },
  invest: {
    label: '投资',
    color: '--accent-green',
    colorHex: '#00ffaa',
    commands: [
      { label: '分析AAPL', icon: <TrendingUp size={14} /> },
      { label: '查看持仓', icon: <BarChart3 size={14} /> },
      { label: '回测策略', icon: <Target size={14} /> },
      { label: '大师投票', icon: <Brain size={14} /> },
      { label: '风控报告', icon: <Shield size={14} /> },
      { label: '市场扫描', icon: <ScanSearch size={14} /> },
    ],
  },
  execute: {
    label: '执行',
    color: '--accent-amber',
    colorHex: '#fbbf24',
    commands: [
      { label: '发布推文', icon: <Send size={14} /> },
      { label: '批量操作', icon: <Zap size={14} /> },
      { label: '定时任务', icon: <Clock size={14} /> },
      { label: '数据导出', icon: <BarChart3 size={14} /> },
      { label: '系统检查', icon: <Cpu size={14} /> },
      { label: '日志查看', icon: <History size={14} /> },
    ],
  },
  create: {
    label: '创作',
    color: '--accent-purple',
    colorHex: '#a78bfa',
    commands: [
      { label: '写文章', icon: <PenTool size={14} /> },
      { label: '生成图片', icon: <Palette size={14} /> },
      { label: '视频脚本', icon: <Sparkles size={14} /> },
      { label: '营销文案', icon: <BookOpen size={14} /> },
      { label: '代码生成', icon: <Cpu size={14} /> },
      { label: '头脑风暴', icon: <Brain size={14} /> },
    ],
  },
};

/* ========== 模拟数据 ========== */

/** 初始对话消息（投资模式下的分析场景） */
const MOCK_MESSAGES: ChatMessage[] = [
  {
    id: '1',
    role: 'user',
    content: '帮我分析一下苹果公司最近的财报表现，重点看营收和利润趋势。',
    timestamp: '14:32',
  },
  {
    id: '2',
    role: 'ai',
    content:
      '苹果 2025 Q1 财报概要：\n\n营收 $1243 亿，同比增长 4.2%，iPhone 收入占比 52%，服务业务收入创历史新高达 $268 亿。\n\n净利润 $367 亿，毛利率 46.9%，同比提升 1.2 个百分点。大中华区营收恢复增长，同比 +11%。\n\n整体偏正面，但硬件增速放缓，服务业务是新增长引擎。',
    timestamp: '14:32',
  },
  {
    id: '3',
    role: 'user',
    content: '七大师对 AAPL 当前价位怎么看？值得加仓吗？',
    timestamp: '14:35',
  },
  {
    id: '4',
    role: 'ai',
    content:
      '七大师投票结果：\n\n✅ 巴菲特 — 买入（护城河稳固，服务收入持续增长）\n✅ 芒格 — 买入（品牌溢价+生态锁定）\n⚠️ 达里奥 — 观望（估值偏高，等待回调）\n✅ 彼得·林奇 — 买入（PEG 合理）\n⚠️ 索罗斯 — 观望（宏观不确定性大）\n✅ 格雷厄姆 — 买入（现金流充裕）\n✅ 费雪 — 买入（长期成长逻辑不变）\n\n综合：5 票买入 / 2 票观望，建议分批建仓。',
    timestamp: '14:35',
  },
  {
    id: '5',
    role: 'ai',
    content:
      '补充一下风控提示：当前 AAPL 已占你组合的 18%，加仓后将超过 20% 的单只持仓上限。建议先评估整体仓位配置后再决定。需要我生成持仓再平衡方案吗？',
    timestamp: '14:36',
  },
];

/** 模拟会话列表 */
const MOCK_SESSIONS: SessionRecord[] = [
  { id: 's1', title: 'AAPL 财报深度分析', time: '今天 14:32', count: 12 },
  { id: 's2', title: '组合再平衡方案', time: '昨天 09:15', count: 8 },
  { id: 's3', title: 'A 股板块轮动追踪', time: '04/17 16:40', count: 23 },
  { id: 's4', title: '加密货币周报生成', time: '04/16 21:05', count: 6 },
];

/* ========== 组件 ========== */

export function Assistant() {
  /* --- 状态 --- */
  const [mode, setMode] = useState<AssistantMode>('invest');
  const [messages, setMessages] = useState<ChatMessage[]>(MOCK_MESSAGES);
  const [input, setInput] = useState('');
  const [sessions] = useState<SessionRecord[]>(MOCK_SESSIONS);

  /* 滚动到底部 */
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const cfg = MODE_CONFIG[mode];

  /** 发送消息（纯模拟） */
  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    const now = new Date();
    const ts = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: 'user', content: text, timestamp: ts },
    ]);
    setInput('');
    // 模拟 AI 回复
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'ai',
          content: '收到，正在为你处理中…',
          timestamp: ts,
        },
      ]);
    }, 600);
  };

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
          <AnimatePresence initial>
            {messages.map((msg, i) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06, duration: 0.35 }}
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
                  style={
                    msg.role === 'user'
                      ? { borderColor: `${cfg.colorHex}30` }
                      : undefined
                  }
                >
                  {/* 消息内容 — 保留换行 */}
                  <div className="whitespace-pre-wrap text-[var(--text-primary)]">{msg.content}</div>
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
            style={{
              // 聚焦时边框发光 — 通过 CSS 自定义属性控制
              boxShadow: `0 0 0 0px ${cfg.colorHex}00`,
            }}
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
              placeholder="输入消息..."
              className={clsx(
                'flex-1 bg-transparent text-sm text-[var(--text-primary)] font-body',
                'placeholder:text-[var(--text-tertiary)] outline-none',
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
              className="w-8 h-8 rounded-xl flex items-center justify-center transition-colors"
              style={{
                background: input.trim() ? cfg.colorHex : 'rgba(255,255,255,0.06)',
                color: input.trim() ? 'var(--bg-base)' : 'var(--text-tertiary)',
              }}
            >
              <Send size={14} />
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
                onClick={() => setInput(cmd.label)}
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
          <h3 className="text-label text-xs font-display mb-3 flex items-center gap-1.5">
            <History size={12} className="text-[var(--text-tertiary)]" />
            会话记录
          </h3>
          <div className="space-y-2">
            {sessions.map((s, i) => (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className={clsx(
                  'flex items-start justify-between gap-2 px-3 py-2.5 rounded-xl cursor-pointer',
                  'hover:bg-white/[0.03] transition-colors duration-200',
                  i === 0 && 'bg-white/[0.02]',
                )}
              >
                <div className="min-w-0">
                  <div className="text-xs text-[var(--text-primary)] truncate">{s.title}</div>
                  <div className="text-[10px] font-mono text-[var(--text-tertiary)] mt-0.5">
                    {s.time}
                  </div>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0 mt-0.5">
                  <MessageSquare size={10} className="text-[var(--text-tertiary)]" />
                  <span className="text-[10px] font-mono text-[var(--text-tertiary)]">{s.count}</span>
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
              { label: '模型', value: 'GPT-4o', color: cfg.colorHex },
              { label: '响应时间', value: '1.2s', color: '#00ffaa' },
              { label: '本次 Tokens', value: '3,847', color: '#fbbf24' },
              { label: '记忆条目', value: '128', color: '#a78bfa' },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between">
                <span className="text-[11px] text-[var(--text-tertiary)]">{item.label}</span>
                <span
                  className="text-xs font-mono font-medium"
                  style={{ color: item.color }}
                >
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
