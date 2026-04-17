/**
 * Portfolio — 我的资产页面
 * 4 个 Tab：持仓概览 | 交易决策 | 自动交易 | 回测分析
 * 集成 IBKR 实盘持仓、AI 团队投票、自动交易开关、策略回测
 */
import { useState } from 'react';
import { motion } from 'framer-motion';
import {
  TrendingUp,
  TrendingDown,
  Loader2,
  Search,
  Play,
  AlertCircle,
  BarChart3,
  DollarSign,
  PieChart as PieChartIcon,
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, LineChart, Line, XAxis, YAxis, CartesianGrid, Legend } from 'recharts';
import clsx from 'clsx';

/* 组件导入 */
import { GlassCard, AnimatedNumber, ToggleSwitch } from '../shared';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { AIVoteCard } from './AIVoteCard';

/* Hooks 导入 */
import {
  usePositions,
  usePnL,
  useTradingControls,
  useAIVote,
  useBacktest,
  type Position,
} from '../../hooks/usePortfolioAPI';

/* ══════════════════════════════════════
 * Tab 1: 持仓概览
 * ══════════════════════════════════════ */

/** 持仓饼图颜色 */
const PIE_COLORS = [
  'var(--oc-brand)',
  'var(--oc-success)',
  'var(--oc-warning)',
  '#8b5cf6', // purple
  '#ec4899', // pink
  '#f59e0b', // amber
  '#10b981', // emerald
  '#3b82f6', // blue
];

function PositionsOverview() {
  const { positions, loading, error } = usePositions(60000); // 60秒轮询
  const { pnl } = usePnL(60000);

  if (loading && !positions) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 size={32} className="text-[var(--oc-brand)] animate-spin" />
      </div>
    );
  }

  if (error || !positions) {
    return (
      <GlassCard className="flex items-center justify-center h-96">
        <div className="text-center">
          <AlertCircle size={48} className="text-[var(--oc-danger)] mx-auto mb-3" />
          <p className="text-sm text-gray-400">无法加载持仓数据</p>
          <p className="text-xs text-gray-500 mt-1">{error || '请检查 IBKR 连接'}</p>
        </div>
      </GlassCard>
    );
  }

  /* 准备饼图数据 */
  const pieData = positions.positions.map((p) => ({
    name: p.symbol,
    value: p.market_value,
  }));

  /* 今日盈亏 */
  const dailyPnl = pnl?.daily_pnl || 0;
  const dailyPnlPct = pnl?.daily_pnl_pct || 0;
  const isPositive = dailyPnl >= 0;

  return (
    <div className="space-y-4">
      {/* 顶部汇总栏 */}
      <GlassCard hoverable={false}>
        <div className="flex items-center justify-between">
          {/* 总市值 */}
          <div>
            <p className="text-xs text-gray-400 mb-1">总市值</p>
            <p className="text-3xl font-bold text-white oc-tabular-nums">
              ${positions.total_market_value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>

          {/* 今日盈亏 */}
          <div className="text-right">
            <p className="text-xs text-gray-400 mb-1">今日盈亏</p>
            <div className="flex items-center gap-2">
              <AnimatedNumber
                value={dailyPnl}
                decimals={2}
                prefix="$"
                colored
                className="text-xl font-bold"
              />
              {isPositive ? (
                <TrendingUp size={20} className="text-[var(--oc-success)]" />
              ) : (
                <TrendingDown size={20} className="text-[var(--oc-danger)]" />
              )}
              <AnimatedNumber
                value={dailyPnlPct}
                decimals={2}
                suffix="%"
                colored
                className="text-sm font-medium"
              />
            </div>
          </div>

          {/* 持仓数量 */}
          <div className="text-right">
            <p className="text-xs text-gray-400 mb-1">持仓数量</p>
            <p className="text-2xl font-bold text-white">{positions.positions.length} 只</p>
          </div>
        </div>
      </GlassCard>

      {/* 饼图 + 持仓列表 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左侧：饼图 */}
        <GlassCard hoverable={false}>
          <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <PieChartIcon size={16} />
            持仓分布
          </h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={(entry) => `${entry.name} ${((entry.value / positions.total_market_value) * 100).toFixed(1)}%`}
                  outerRadius={90}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {pieData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    border: '1px solid rgba(75, 85, 99, 0.3)',
                    borderRadius: '8px',
                    color: '#fff',
                  }}
                  formatter={(value: number) => `$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-500 text-sm">
              暂无持仓
            </div>
          )}
        </GlassCard>

        {/* 右侧：持仓列表 */}
        <GlassCard hoverable={false} className="overflow-hidden">
          <h3 className="text-sm font-semibold text-gray-300 mb-4">持仓明细</h3>
          <div className="space-y-2 max-h-[280px] overflow-y-auto pr-2">
            {positions.positions.map((pos) => (
              <PositionRow key={pos.symbol} position={pos} />
            ))}
            {positions.positions.length === 0 && (
              <p className="text-sm text-gray-500 text-center py-8">暂无持仓</p>
            )}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

/** 单个持仓行 */
function PositionRow({ position }: { position: Position }) {
  const isProfit = position.unrealized_pnl >= 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-3 rounded-lg bg-dark-700/50 hover:bg-dark-600/50 transition-colors"
    >
      <div className="flex items-center justify-between mb-2">
        <div>
          <p className="text-sm font-bold text-white">{position.symbol}</p>
          <p className="text-xs text-gray-400">{position.quantity} 股</p>
        </div>
        <div className="text-right">
          <p className="text-sm font-semibold text-white oc-tabular-nums">
            ${position.current_price.toFixed(2)}
          </p>
          <p className={clsx('text-xs font-medium oc-tabular-nums', isProfit ? 'text-[var(--oc-success)]' : 'text-[var(--oc-danger)]')}>
            {isProfit ? '+' : ''}{position.unrealized_pnl_pct.toFixed(2)}%
          </p>
        </div>
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">
          市值 <span className="text-gray-300 font-medium oc-tabular-nums">${position.market_value.toFixed(2)}</span>
        </span>
        <span className="text-gray-500">
          成本 <span className="text-gray-300 font-medium oc-tabular-nums">${position.avg_cost.toFixed(2)}</span>
        </span>
        <span className={clsx('font-medium oc-tabular-nums', isProfit ? 'text-[var(--oc-success)]' : 'text-[var(--oc-danger)]')}>
          {isProfit ? '+' : ''}${position.unrealized_pnl.toFixed(2)}
        </span>
      </div>
    </motion.div>
  );
}

/* ══════════════════════════════════════
 * Tab 2: 交易决策
 * ══════════════════════════════════════ */

function TradingDecision() {
  const [symbol, setSymbol] = useState('');
  const { voteResult, voting, voteError, triggerVote } = useAIVote();

  const handleVote = () => {
    if (symbol.trim()) {
      triggerVote(symbol.trim().toUpperCase());
    }
  };

  return (
    <div className="space-y-4">
      {/* 输入区域 */}
      {!voteResult && !voting && (
        <GlassCard hoverable={false}>
          <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
            <Search size={16} />
            AI 团队分析
          </h3>
          <p className="text-xs text-gray-500 mb-4">
            输入股票代码，6 个 AI 分析师会分别给出买入/持有/跳过建议，并进行团队投票
          </p>
          <div className="flex gap-3">
            <Input
              type="text"
              placeholder="输入代码，如 AAPL"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && symbol.trim()) {
                  handleVote();
                }
              }}
              className="flex-1"
            />
            <Button
              onClick={handleVote}
              disabled={!symbol.trim()}
              className="px-6"
            >
              <BarChart3 size={16} />
              分析
            </Button>
          </div>
          {voteError && (
            <p className="text-xs text-[var(--oc-danger)] mt-2">{voteError}</p>
          )}
        </GlassCard>
      )}

      {/* AI 投票卡片 */}
      <AIVoteCard
        result={voteResult}
        loading={voting}
        error={voteError}
        onTriggerVote={(sym) => {
          setSymbol(sym);
          triggerVote(sym);
        }}
      />
    </div>
  );
}

/* ══════════════════════════════════════
 * Tab 3: 自动交易
 * ══════════════════════════════════════ */

function AutoTrading() {
  const { controls, loading, saving, update } = useTradingControls();
  const [strategy, setStrategy] = useState<'conservative' | 'balanced' | 'aggressive'>('balanced');

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 size={32} className="text-[var(--oc-brand)] animate-spin" />
      </div>
    );
  }

  if (!controls) {
    return (
      <GlassCard className="flex items-center justify-center h-96">
        <div className="text-center">
          <AlertCircle size={48} className="text-[var(--oc-danger)] mx-auto mb-3" />
          <p className="text-sm text-gray-400">无法加载交易控制</p>
        </div>
      </GlassCard>
    );
  }

  const handleToggle = async (checked: boolean) => {
    try {
      await update({ auto_trader_enabled: checked });
    } catch (e) {
      console.error('更新失败:', e);
    }
  };

  return (
    <div className="space-y-4">
      {/* 主开关 */}
      <GlassCard hoverable={false}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white mb-1">自动交易</h3>
            <p className="text-xs text-gray-400">
              {controls.auto_trader_enabled ? '系统正在自动执行交易策略' : '手动模式，需要人工确认'}
            </p>
          </div>
          <ToggleSwitch
            checked={controls.auto_trader_enabled}
            onChange={handleToggle}
            disabled={saving}
            size="lg"
          />
        </div>
      </GlassCard>

      {/* 策略选择 */}
      <GlassCard hoverable={false}>
        <h3 className="text-sm font-semibold text-gray-300 mb-4">交易策略</h3>
        <div className="flex gap-3">
          {(['conservative', 'balanced', 'aggressive'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStrategy(s)}
              className={clsx(
                'flex-1 py-3 px-4 rounded-lg border-2 transition-all',
                strategy === s
                  ? 'border-[var(--oc-brand)] bg-[var(--oc-brand)]/10'
                  : 'border-dark-600 bg-dark-700/30 hover:border-dark-500'
              )}
            >
              <p className={clsx('text-sm font-semibold', strategy === s ? 'text-[var(--oc-brand)]' : 'text-gray-300')}>
                {s === 'conservative' ? '保守' : s === 'balanced' ? '均衡' : '激进'}
              </p>
            </button>
          ))}
        </div>
      </GlassCard>

      {/* 风险参数 */}
      <GlassCard hoverable={false}>
        <h3 className="text-sm font-semibold text-gray-300 mb-4">风险参数</h3>
        <div className="grid grid-cols-3 gap-4">
          <div className="p-3 rounded-lg bg-dark-700/50">
            <p className="text-xs text-gray-400 mb-1">单笔风险上限</p>
            <p className="text-lg font-bold text-white">2%</p>
          </div>
          <div className="p-3 rounded-lg bg-dark-700/50">
            <p className="text-xs text-gray-400 mb-1">日亏限额</p>
            <p className="text-lg font-bold text-white">$100</p>
          </div>
          <div className="p-3 rounded-lg bg-dark-700/50">
            <p className="text-xs text-gray-400 mb-1">盈亏比</p>
            <p className="text-lg font-bold text-white">≥1:2</p>
          </div>
        </div>
      </GlassCard>

      {/* 今日交易历史 */}
      <GlassCard hoverable={false}>
        <h3 className="text-sm font-semibold text-gray-300 mb-4">今日交易</h3>
        <div className="text-center py-8 text-gray-500 text-sm">
          暂无交易记录
        </div>
      </GlassCard>
    </div>
  );
}

/* ══════════════════════════════════════
 * Tab 4: 回测分析
 * ══════════════════════════════════════ */

function BacktestAnalysis() {
  const [symbol, setSymbol] = useState('');
  const [strategy, setStrategy] = useState('ma_cross');
  const [period, setPeriod] = useState('1y');
  const { backtestResult, backtesting, backtestError, runBacktest } = useBacktest();

  const handleRun = () => {
    if (symbol.trim()) {
      runBacktest(symbol.trim().toUpperCase(), strategy, period);
    }
  };

  return (
    <div className="space-y-4">
      {/* 参数选择 */}
      <GlassCard hoverable={false}>
        <h3 className="text-sm font-semibold text-gray-300 mb-4">回测参数</h3>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-gray-400 mb-2 block">股票代码</label>
            <Input
              type="text"
              placeholder="如 AAPL"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-2 block">策略</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full h-8 rounded-lg border border-input bg-dark-700 px-2.5 text-sm text-white"
            >
              <option value="ma_cross">均线交叉</option>
              <option value="rsi">RSI 超买超卖</option>
              <option value="macd">MACD</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-2 block">周期</label>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="w-full h-8 rounded-lg border border-input bg-dark-700 px-2.5 text-sm text-white"
            >
              <option value="3mo">3 个月</option>
              <option value="6mo">6 个月</option>
              <option value="1y">1 年</option>
              <option value="2y">2 年</option>
            </select>
          </div>
        </div>
        <Button
          onClick={handleRun}
          disabled={!symbol.trim() || backtesting}
          className="w-full mt-4"
        >
          {backtesting ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              回测中...
            </>
          ) : (
            <>
              <Play size={16} />
              开始回测
            </>
          )}
        </Button>
        {backtestError && (
          <p className="text-xs text-[var(--oc-danger)] mt-2">{backtestError}</p>
        )}
      </GlassCard>

      {/* 回测结果 */}
      {backtestResult && (
        <>
          {/* 关键指标 */}
          <div className="grid grid-cols-4 gap-3">
            <GlassCard hoverable={false} className="text-center">
              <p className="text-xs text-gray-400 mb-1">胜率</p>
              <p className="text-2xl font-bold text-[var(--oc-success)]">
                {(backtestResult.win_rate * 100).toFixed(1)}%
              </p>
            </GlassCard>
            <GlassCard hoverable={false} className="text-center">
              <p className="text-xs text-gray-400 mb-1">总收益</p>
              <p className={clsx('text-2xl font-bold', backtestResult.total_return >= 0 ? 'text-[var(--oc-success)]' : 'text-[var(--oc-danger)]')}>
                {backtestResult.total_return >= 0 ? '+' : ''}{backtestResult.total_return.toFixed(2)}%
              </p>
            </GlassCard>
            <GlassCard hoverable={false} className="text-center">
              <p className="text-xs text-gray-400 mb-1">最大回撤</p>
              <p className="text-2xl font-bold text-[var(--oc-danger)]">
                {backtestResult.max_drawdown.toFixed(2)}%
              </p>
            </GlassCard>
            <GlassCard hoverable={false} className="text-center">
              <p className="text-xs text-gray-400 mb-1">夏普比率</p>
              <p className="text-2xl font-bold text-white">
                {backtestResult.sharpe_ratio.toFixed(2)}
              </p>
            </GlassCard>
          </div>

          {/* 权益曲线 */}
          <GlassCard hoverable={false}>
            <h3 className="text-sm font-semibold text-gray-300 mb-4">权益曲线</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={backtestResult.chart_data}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(75, 85, 99, 0.2)" />
                <XAxis
                  dataKey="time"
                  stroke="#9ca3af"
                  style={{ fontSize: '12px' }}
                />
                <YAxis
                  stroke="#9ca3af"
                  style={{ fontSize: '12px' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    border: '1px solid rgba(75, 85, 99, 0.3)',
                    borderRadius: '8px',
                    color: '#fff',
                  }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="var(--oc-brand)"
                  strokeWidth={2}
                  dot={false}
                  name="策略"
                />
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  stroke="#9ca3af"
                  strokeWidth={2}
                  dot={false}
                  strokeDasharray="5 5"
                  name="基准"
                />
              </LineChart>
            </ResponsiveContainer>
          </GlassCard>
        </>
      )}
    </div>
  );
}

/* ══════════════════════════════════════
 * 主组件: Portfolio
 * ══════════════════════════════════════ */

export function Portfolio() {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="h-full flex flex-col p-6">
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList variant="line" className="mb-6">
          <TabsTrigger value="overview">持仓概览</TabsTrigger>
          <TabsTrigger value="decision">交易决策</TabsTrigger>
          <TabsTrigger value="auto">自动交易</TabsTrigger>
          <TabsTrigger value="backtest">回测分析</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <PositionsOverview />
        </TabsContent>

        <TabsContent value="decision">
          <TradingDecision />
        </TabsContent>

        <TabsContent value="auto">
          <AutoTrading />
        </TabsContent>

        <TabsContent value="backtest">
          <BacktestAnalysis />
        </TabsContent>
      </Tabs>
    </div>
  );
}
