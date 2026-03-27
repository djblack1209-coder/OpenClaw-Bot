import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  DollarSign, TrendingUp, Search, ShieldAlert, FileBarChart,
  RotateCcw, LineChart, Target, Activity, PieChart,
  Play, Loader2, ArrowUpRight, ArrowDownRight, Briefcase
} from 'lucide-react';
import clsx from 'clsx';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface ActionStatus {
  running: boolean;
  lastResult?: string;
  error?: string;
}

const actions = [
  { id: 'money', label: '收入看板', desc: '盈利总控台，查看收入与资产概览', icon: DollarSign, cmd: '/money' },
  { id: 'brief', label: 'PnL 日报', desc: '每日盈亏报告与下场指令', icon: FileBarChart, cmd: '/brief' },
  { id: 'invest', label: '投资分析', desc: '协作式投资分析与建议', icon: Search, cmd: '/invest', hasInput: true, placeholder: '分析话题 (如 TSLA财报)' },
  { id: 'quote', label: '实时行情', desc: '查询股票/加密货币实时行情', icon: LineChart, cmd: '/quote', hasInput: true, placeholder: '代码 (如 AAPL, BTC)' },
  { id: 'scan', label: '市场扫描', desc: '扫描市场机会与异动', icon: Target, cmd: '/scan' },
  { id: 'ta', label: '技术分析', desc: '技术指标分析与图表', icon: Activity, cmd: '/ta', hasInput: true, placeholder: '代码 (如 NVDA)' },
  { id: 'signal', label: '交易信号', desc: '生成交易信号与建议', icon: TrendingUp, cmd: '/signal', hasInput: true, placeholder: '代码' },
  { id: 'risk', label: '风险检查', desc: '交易风险控制与止损回撤管理', icon: ShieldAlert, cmd: '/risk' },
  { id: 'monitor', label: '持仓监控', desc: '实时监控持仓与盈亏', icon: PieChart, cmd: '/monitor' },
  { id: 'backtest', label: '回测策略', desc: '策略历史回测与验证', icon: RotateCcw, cmd: '/backtest', hasInput: true, placeholder: '策略描述' },
  { id: 'rebalance', label: '再平衡', desc: '组合再平衡建议', icon: Target, cmd: '/rebalance' },
];

interface AssetItem {
  name: string;
  value: number;
  pnl: number;
}

interface ChartDataPoint {
  name: string;
  value: number;
}

export function Money() {
  const [statuses, setStatuses] = useState<Record<string, ActionStatus>>({});
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [ibkrConnected, setIbkrConnected] = useState(false);
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [, setDataLoading] = useState(true);

  // 尝试从后端获取交易数据
  useEffect(() => {
    const fetchTradingData = async () => {
      try {
        const resp = await fetch('http://127.0.0.1:18790/api/v1/trading/status');
        if (resp.ok) {
          const data = await resp.json();
          setIbkrConnected(data.connected ?? false);
          if (data.chart_data) setChartData(data.chart_data);
          if (data.assets) setAssets(data.assets);
        }
      } catch {
        // 后端不可达时保持默认的断开状态
      } finally {
        setDataLoading(false);
      }
    };
    fetchTradingData();
  }, []);

  const handleAction = async (id: string, cmd: string, hasInput?: boolean) => {
    const input = inputs[id];
    if (hasInput && !input) return;

    setStatuses(prev => ({ ...prev, [id]: { running: true } }));

    try {
      const resp = await fetch('http://127.0.0.1:18790/api/v1/omega/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: `${cmd} ${input || ''}`.trim() }),
      });
      const data = await resp.json();
      setStatuses(prev => ({
        ...prev,
        [id]: { running: false, lastResult: data.result || data.response || '执行完成' }
      }));
    } catch (e) {
      setStatuses(prev => ({
        ...prev,
        [id]: { running: false, lastResult: `执行失败: ${e instanceof Error ? e.message : '服务不可达'}` }
      }));
    }
  };

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2 pb-10">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header & IBKR Status */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-dark-800/40 p-4 rounded-2xl border border-dark-600/50 backdrop-blur-sm">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <DollarSign className="text-green-400 h-6 w-6" />
              盈利总控台
            </h2>
            <p className="text-gray-400 text-sm mt-1">管理量化交易、行情监控、Alpha 研究与盈亏分析</p>
          </div>
          
          <div className={clsx(
            "flex items-center gap-2.5 px-4 py-2 rounded-full border shadow-sm",
            ibkrConnected ? "bg-green-500/10 border-green-500/20" : "bg-red-500/10 border-red-500/20"
          )}>
            <div className="relative flex h-2.5 w-2.5">
              {ibkrConnected && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>}
              <span className={clsx("relative inline-flex rounded-full h-2.5 w-2.5", ibkrConnected ? "bg-green-500" : "bg-red-500")}></span>
            </div>
            <span className={clsx("text-sm font-semibold tracking-wide", ibkrConnected ? "text-green-400" : "text-red-400")}>
              {ibkrConnected ? "IBKR 网关在线" : "IBKR 已断开"}
            </span>
          </div>
        </div>

        {/* Dashboard Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2 bg-dark-900 border-dark-600 shadow-xl overflow-hidden">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg font-semibold text-white flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <LineChart className="text-claw-400" size={18} />
                  组合净值表现
                </div>
                {chartData.length > 0 && (
                <div className="text-2xl font-bold text-green-400 flex items-center gap-1">
                  ${chartData[chartData.length - 1]?.value.toLocaleString('en-US', { minimumFractionDigits: 2 })} <ArrowUpRight size={20} className="text-green-400" />
                </div>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[250px] w-full mt-4">
                {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#4ade80" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#4ade80" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2e2e33" vertical={false} />
                    <XAxis dataKey="name" stroke="#52525b" fontSize={12} tickLine={false} axisLine={false} />
                    <YAxis stroke="#52525b" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `$${val}`} domain={['dataMin - 100', 'dataMax + 100']} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1a1a1d', borderColor: '#3d3d44', color: '#fff', borderRadius: '8px' }}
                      itemStyle={{ color: '#4ade80', fontWeight: 'bold' }}
                      formatter={(value) => [`$${value}`, 'Net Value']}
                    />
                    <Area type="monotone" dataKey="value" stroke="#4ade80" strokeWidth={2} fillOpacity={1} fill="url(#colorValue)" />
                  </AreaChart>
                </ResponsiveContainer>
                ) : (
                <div className="h-full flex flex-col items-center justify-center text-gray-500 gap-3">
                  <LineChart size={40} className="text-dark-600" />
                  <p className="text-sm">暂无数据，请先启动交易系统</p>
                </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-dark-900 border-dark-600 shadow-xl overflow-hidden">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg font-semibold text-white flex items-center gap-2">
                <Briefcase className="text-purple-400" size={18} />
                核心持仓
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4 mt-2">
                {assets.length > 0 ? assets.map((asset) => (
                  <div key={asset.name} className="flex items-center justify-between p-3 rounded-lg bg-dark-800 border border-dark-700/50">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded bg-dark-700 flex items-center justify-center font-bold text-xs text-white">
                        {asset.name.substring(0, 2)}
                      </div>
                      <div>
                        <p className="text-sm font-bold text-white">{asset.name}</p>
                        <p className="text-xs text-gray-500 font-mono">${asset.value}</p>
                      </div>
                    </div>
                    <div className={clsx(
                      "flex items-center gap-1 text-sm font-bold",
                      asset.pnl > 0 ? "text-green-400" : asset.pnl < 0 ? "text-red-400" : "text-gray-400"
                    )}>
                      {asset.pnl > 0 ? <ArrowUpRight size={14} /> : asset.pnl < 0 ? <ArrowDownRight size={14} /> : null}
                      {Math.abs(asset.pnl)}%
                    </div>
                  </div>
                )) : (
                <div className="flex flex-col items-center justify-center py-8 text-gray-500 gap-2">
                  <Briefcase size={32} className="text-dark-600" />
                  <p className="text-sm">暂无持仓数据</p>
                </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Action Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {actions.map((action) => {
            const status = statuses[action.id];
            const isRunning = status?.running;
            
            return (
              <Card key={action.id} className="bg-dark-800/80 border-dark-600 shadow-md hover:border-claw-500/50 transition-all overflow-hidden group">
                <div className="p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div className="w-10 h-10 rounded-xl bg-dark-700 border border-dark-600 flex items-center justify-center group-hover:scale-110 transition-transform">
                      <action.icon size={20} className="text-claw-400" />
                    </div>
                    <button
                      onClick={() => handleAction(action.id, action.cmd, action.hasInput)}
                      disabled={isRunning || (action.hasInput && !inputs[action.id])}
                      className={clsx(
                        "w-8 h-8 rounded-full flex items-center justify-center transition-colors",
                        isRunning ? "bg-dark-600" : "bg-claw-500/10 text-claw-400 hover:bg-claw-500 hover:text-white"
                      )}
                    >
                      {isRunning ? <Loader2 size={16} className="animate-spin text-gray-400" /> : <Play size={14} className="ml-0.5" />}
                    </button>
                  </div>
                  
                  <h3 className="font-bold text-white mb-1">{action.label}</h3>
                  <p className="text-xs text-gray-400 mb-4 h-8 line-clamp-2">{action.desc}</p>
                  
                  {action.hasInput ? (
                    <input
                      type="text"
                      placeholder={action.placeholder}
                      value={inputs[action.id] || ''}
                      onChange={(e) => setInputs(prev => ({ ...prev, [action.id]: e.target.value }))}
                      onKeyDown={(e) => e.key === 'Enter' && handleAction(action.id, action.cmd, true)}
                      className="w-full bg-dark-900 border border-dark-700 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:border-claw-500/50 focus:ring-1 focus:ring-claw-500/50 transition-all placeholder:text-dark-400"
                    />
                  ) : (
                    <div className="h-[38px] flex items-center">
                      <code className="text-[10px] bg-dark-900 px-2 py-1 rounded text-gray-500 border border-dark-700 font-mono">
                        {action.cmd}
                      </code>
                    </div>
                  )}

                  {/* Result Area */}
                  <AnimatePresence>
                    {status?.lastResult && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="mt-3 pt-3 border-t border-dark-700"
                      >
                        <p className="text-xs text-green-400 font-mono break-words bg-green-500/10 p-2 rounded border border-green-500/20">
                          {status.lastResult}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}
