/* Bot 投票数据 */
interface BotVote {
  name: string;
  signal: 'approve' | 'reject' | 'pending' | 'abstain';
  confidence: number;
}

interface Props {
  bots: BotVote[];
  dailyPnl: number;
  dailyPnlPct: number;
  isRunning: boolean;
}

/* 信号对应的颜色 */
const signalColors: Record<BotVote['signal'], string> = {
  approve: 'var(--accent-green)',
  reject: 'var(--accent-red)',
  pending: 'var(--accent-amber)',
  abstain: 'var(--text-disabled)',
};

/**
 * 交易引擎卡片 — 首页 hero 区域
 * 展示 7-Bot 投票共识条 + 每日盈亏
 */
export function TradingEngineCard({ bots, dailyPnl, dailyPnlPct, isRunning }: Props) {
  /* 计算各信号计数 */
  const counts = bots.reduce(
    (acc, b) => { acc[b.signal] = (acc[b.signal] || 0) + 1; return acc; },
    {} as Record<string, number>,
  );

  /* PnL 格式化 */
  const pnlSign = dailyPnl >= 0 ? '+' : '';
  const pnlColor = dailyPnl >= 0 ? 'var(--color-profit)' : 'var(--color-loss)';

  return (
    <div className="abyss-card p-6 h-full flex flex-col">
      {/* 头部标签行 */}
      <div className="flex items-center justify-between">
        <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
          IBKR 实盘 // 自动交易引擎
        </span>
        <div className="status-live">
          <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
          <span style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}>
            {isRunning ? 'LIVE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* 标题 */}
      <h2 className="text-hero text-[32px] mt-3" style={{ color: 'var(--text-primary)' }}>
        交易引擎
      </h2>

      {/* 中间区域：共识条 + PnL */}
      <div className="flex-1 flex flex-col lg:flex-row lg:items-end gap-6 mt-6">
        {/* 左侧：共识可视化 */}
        <div className="flex-1">
          <span className="text-label text-[10px]">7-BOT 投票共识</span>

          {/* 投票进度条组 */}
          <div className="space-y-2 mt-3">
            {bots.length > 0 ? (
              bots.map((bot, i) => (
                <div key={bot.name || i} className="flex items-center gap-3">
                  <span
                    className="font-mono text-[10px] w-20 truncate"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {bot.name || `BOT_${i + 1}`}
                  </span>
                  <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${Math.max(bot.confidence * 100, 8)}%`,
                        background: signalColors[bot.signal],
                        opacity: 0.85,
                      }}
                    />
                  </div>
                  <span
                    className="font-mono text-[9px] uppercase w-14 text-right"
                    style={{ color: signalColors[bot.signal] }}
                  >
                    {{ approve: '买入', reject: '卖出', pending: '待定', abstain: '弃权' }[bot.signal]}
                  </span>
                </div>
              ))
            ) : (
              /* 无 Bot 数据时的空状态提示 */
              <div className="flex flex-col items-center justify-center py-6 text-center">
                <span className="text-[11px] text-[var(--text-tertiary)] font-mono">等待 Bot 投票数据...</span>
                <span className="text-[10px] text-[var(--text-disabled)] mt-1">启动交易引擎后自动加载</span>
              </div>
            )}
          </div>

          {/* 共识总结 */}
          {bots.length > 0 && (
            <div className="flex gap-4 mt-3">
              {['approve', 'reject', 'pending'].map((sig) => (
                <span key={sig} className="flex items-center gap-1">
                  <span
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ background: signalColors[sig as BotVote['signal']] }}
                  />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                    {counts[sig] || 0}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 右侧：Daily PnL */}
        <div className="lg:text-right flex-shrink-0">
          <span className="text-label">今日盈亏</span>
          <div
            className="text-hero text-[42px] mt-1 font-mono tabular-nums"
            style={{ color: pnlColor }}
          >
            {pnlSign}${Math.abs(dailyPnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <span
            className="font-mono text-sm tabular-nums"
            style={{ color: pnlColor, opacity: 0.7 }}
          >
            {pnlSign}{dailyPnlPct.toFixed(2)}%
          </span>
        </div>
      </div>
    </div>
  );
}
