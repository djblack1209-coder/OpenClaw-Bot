/**
 * AIVoteCard — AI 团队投票可视化卡片
 * 展示 6 个 AI 模型的投票结果（买入/持有/跳过）+ 共识信号 + 置信度
 * 设计灵感：Robinhood 分析师评级 + Linear 卡片风格
 */
import { useLanguage } from '../../i18n';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ThumbsUp,
  Minus,
  ThumbsDown,
  ChevronDown,
  ChevronUp,
  Shield,
  Target,
  TrendingUp,
  BarChart3,
  Globe,
  Brain,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import { GlassCard } from '../shared';
import type { BotVote, VoteResult } from '../../hooks/usePortfolioAPI';
import clsx from 'clsx';

/* ── AI 角色配置 ── */
const AI_ROLES: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  haiku:    { label: '雷达哨兵',   icon: Target,      color: 'text-sky-400' },
  qwen:    { label: '宏观分析',   icon: Globe,        color: 'text-violet-400' },
  gpt:     { label: '图表技术',   icon: BarChart3,    color: 'text-emerald-400' },
  deepseek: { label: '风控审计',  icon: Shield,       color: 'text-amber-400' },
  sonnet:  { label: '战术指挥',   icon: TrendingUp,   color: 'text-blue-400' },
  opus:    { label: '首席策略',   icon: Brain,        color: 'text-purple-400' },
};

/* 根据 bot_id 匹配角色（后端 bot_id 可能带前缀/后缀） */
function matchRole(botId: string) {
  const lower = botId.toLowerCase();
  for (const key of Object.keys(AI_ROLES)) {
    if (lower.includes(key)) return AI_ROLES[key];
  }
  return { label: botId, icon: Brain, color: 'text-gray-400' };
}

/* 投票颜色/图标映射 */
function voteStyle(vote: string) {
  switch (vote.toUpperCase()) {
    case 'BUY':  return { bg: 'bg-[var(--oc-success)]/15', text: 'text-[var(--oc-success)]', label: '买入', Icon: ThumbsUp };
    case 'HOLD': return { bg: 'bg-[var(--oc-warning)]/15', text: 'text-[var(--oc-warning)]', label: '持有', Icon: Minus };
    case 'SKIP':
    case 'SELL':
    default:     return { bg: 'bg-[var(--oc-danger)]/15', text: 'text-[var(--oc-danger)]', label: '跳过', Icon: ThumbsDown };
  }
}

/* ── 单个 AI 投票行 ── */
function VoteRow({ vote, index }: { vote: BotVote; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const role = matchRole(vote.bot_id);
  const RoleIcon = role.icon;
  const style = voteStyle(vote.vote);
  const VoteIcon = style.Icon;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.06, duration: 0.25 }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left"
      >
        <div className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-dark-600/50 transition-colors">
          {/* 角色图标 */}
          <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0', 'bg-dark-600')}>
            <RoleIcon size={16} className={role.color} />
          </div>

          {/* 角色名 */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-200 truncate">{role.label}</p>
          </div>

          {/* 置信度条 */}
          <div className="w-16 flex items-center gap-1.5">
            <div className="flex-1 h-1.5 bg-dark-600 rounded-full overflow-hidden">
              <div
                className={clsx('h-full rounded-full transition-all duration-300', style.bg.replace('/15', ''))}
                style={{ width: `${(vote.confidence / 10) * 100}%` }}
              />
            </div>
            <span className="text-xs text-gray-500 w-4 text-right tabular-nums">
              {vote.confidence}
            </span>
          </div>

          {/* 投票标签 */}
          <span className={clsx('px-2 py-0.5 rounded-md text-xs font-semibold', style.bg, style.text)}>
            <VoteIcon size={10} className="inline mr-1" />
            {style.label}
          </span>

          {/* 展开箭头 */}
          {expanded ? <ChevronUp size={14} className="text-gray-500" /> : <ChevronDown size={14} className="text-gray-500" />}
        </div>
      </button>

      {/* 展开详情 */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="ml-11 mr-3 mb-2 p-3 rounded-lg bg-dark-700/50 border border-dark-500/50">
              <p className="text-xs text-gray-300 leading-relaxed">{vote.reasoning || '暂无分析理由'}</p>
              {/* 价格建议 */}
              {(vote.entry_price || vote.stop_loss || vote.take_profit) && (
                <div className="flex gap-4 mt-2 pt-2 border-t border-dark-500/50">
                  {vote.entry_price && (
                    <span className="text-xs text-gray-400">
                      入场 <span className="text-white font-medium">${vote.entry_price.toFixed(2)}</span>
                    </span>
                  )}
                  {vote.stop_loss && (
                    <span className="text-xs text-gray-400">
                      止损 <span className="text-[var(--oc-danger)] font-medium">${vote.stop_loss.toFixed(2)}</span>
                    </span>
                  )}
                  {vote.take_profit && (
                    <span className="text-xs text-gray-400">
                      止盈 <span className="text-[var(--oc-success)] font-medium">${vote.take_profit.toFixed(2)}</span>
                    </span>
                  )}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ── 共识信号大标牌 ── */
function ConsensusHeader({ result }: { result: VoteResult }) {
  const buyCount = result.votes.filter((v) => v.vote.toUpperCase() === 'BUY').length;
  const holdCount = result.votes.filter((v) => v.vote.toUpperCase() === 'HOLD').length;
  const skipCount = result.votes.length - buyCount - holdCount;

  /* 共识颜色 */
  const signalColor = result.passed
    ? 'text-[var(--oc-success)]'
    : result.veto_triggered
      ? 'text-[var(--oc-danger)]'
      : 'text-[var(--oc-warning)]';

  const signalBg = result.passed
    ? 'bg-[var(--oc-success)]/10'
    : result.veto_triggered
      ? 'bg-[var(--oc-danger)]/10'
      : 'bg-[var(--oc-warning)]/10';

  /* 共识文字 */
  const signalText = result.passed
    ? '建议买入'
    : result.veto_triggered
      ? '被否决'
      : '暂不操作';

  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          {result.symbol}
          <span className={clsx('px-2.5 py-1 rounded-lg text-sm font-semibold', signalBg, signalColor)}>
            {signalText}
          </span>
        </h3>
        {result.veto_triggered && (
          <p className="text-xs text-[var(--oc-danger)] mt-1 flex items-center gap-1">
            <AlertTriangle size={12} /> 风控否决：不建议操作
          </p>
        )}
      </div>

      {/* 投票计数条 */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 text-xs">
          <span className="text-[var(--oc-success)] font-bold">{buyCount}</span>
          <span className="text-gray-500">买</span>
        </div>
        <div className="flex items-center gap-1 text-xs">
          <span className="text-[var(--oc-warning)] font-bold">{holdCount}</span>
          <span className="text-gray-500">持</span>
        </div>
        <div className="flex items-center gap-1 text-xs">
          <span className="text-[var(--oc-danger)] font-bold">{skipCount}</span>
          <span className="text-gray-500">过</span>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════
 * 主组件: AIVoteCard
 * ══════════════════════════════════════ */

interface AIVoteCardProps {
  /** 投票结果数据 — null 表示还没投 */
  result: VoteResult | null;
  /** 是否正在投票中 */
  loading?: boolean;
  /** 错误信息 */
  error?: string | null;
  /** 点击"发起投票"的回调 */
  onTriggerVote?: (symbol: string) => void;
  className?: string;
}

export function AIVoteCard({ result, loading, error, onTriggerVote, className }: AIVoteCardProps) {
  const [inputSymbol, setInputSymbol] = useState('');
  const { t } = useLanguage();

  /* 尚未投票 — 展示输入框 */
  if (!result && !loading) {
    return (
      <GlassCard className={className} hoverable={false}>
        <h3 className="text-sm font-semibold text-gray-300 mb-3">{t('portfolio.vote.title')}</h3>
        <p className="text-xs text-gray-500 mb-4">
          输入股票代码，6 个 AI 分析师会分别给出买入/持有/跳过建议
        </p>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder={t('portfolio.vote.placeholder')}
            value={inputSymbol}
            onChange={(e) => setInputSymbol(e.target.value.toUpperCase())}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && inputSymbol.trim()) {
                onTriggerVote?.(inputSymbol.trim());
              }
            }}
            className="input-base flex-1 text-sm"
          />
          <button
            onClick={() => inputSymbol.trim() && onTriggerVote?.(inputSymbol.trim())}
            disabled={!inputSymbol.trim()}
            className="btn-primary px-4 text-sm disabled:opacity-40"
          >
            分析
          </button>
        </div>
        {error && (
          <p className="text-xs text-[var(--oc-danger)] mt-2">{error}</p>
        )}
      </GlassCard>
    );
  }

  /* 投票中 — 加载动画 */
  if (loading) {
    return (
      <GlassCard className={className} hoverable={false}>
        <div className="flex flex-col items-center justify-center py-8">
          <Loader2 size={32} className="text-[var(--oc-brand)] animate-spin mb-3" />
          <p className="text-sm text-gray-300">{t('portfolio.vote.voting')}</p>
          <p className="text-xs text-gray-500 mt-1">{t('portfolio.vote.votingHint')}</p>
        </div>
      </GlassCard>
    );
  }

  /* 有结果 — 展示投票详情 */
  return (
    <GlassCard className={className} hoverable={false}>
      <ConsensusHeader result={result!} />

      {/* 分歧度提示 */}
      {result!.divergence !== undefined && result!.divergence > 2 && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-[var(--oc-warning)]/10 border border-[var(--oc-warning)]/20">
          <p className="text-xs text-[var(--oc-warning)]">
            分歧较大（σ={result!.divergence.toFixed(1)}），各 AI 意见不一致，建议谨慎
          </p>
        </div>
      )}

      {/* 投票列表 */}
      <div className="divide-y divide-dark-600/30">
        {result!.votes.map((vote, i) => (
          <VoteRow key={vote.bot_id} vote={vote} index={i} />
        ))}
      </div>

      {/* 底部：再次投票 */}
      <div className="mt-4 pt-3 border-t border-dark-600 flex items-center justify-between">
        <span className="text-xs text-gray-500">
          {new Date(result!.timestamp).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
        </span>
        <button
          onClick={() => onTriggerVote?.(result!.symbol)}
          className="text-xs text-[var(--oc-brand)] hover:underline"
        >
          重新分析
        </button>
      </div>
    </GlassCard>
  );
}
