import { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, CandlestickData, Time, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Search, Loader2, TrendingUp } from 'lucide-react';
import { clawbotFetch } from '@/lib/tauri';

// K线数据格式（与后端 /trading/kline 接口对齐）
interface KlineDataPoint {
  time: number;   // Unix 时间戳（秒）
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface KlineResponse {
  symbol: string;
  data: KlineDataPoint[];
  error?: string;
}

// 默认标的列表
const DEFAULT_SYMBOLS = ['AAPL', 'NVDA', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'AMD'];
const INTERVALS = [
  { value: '1d', label: '日K' },
  { value: '1h', label: '1小时' },
  { value: '1wk', label: '周K' },
];
const PERIODS = [
  { value: '1mo', label: '1个月' },
  { value: '3mo', label: '3个月' },
  { value: '6mo', label: '6个月' },
  { value: '1y', label: '1年' },
];

export default function KlineChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [symbol, setSymbol] = useState('AAPL');
  const [inputValue, setInputValue] = useState('AAPL');
  const [interval, setInterval] = useState('1d');
  const [period, setPeriod] = useState('3mo');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [priceChange, setPriceChange] = useState<number>(0);

  // 获取K线数据
  const fetchKlineData = async (sym: string, intv: string, prd: string) => {
    setLoading(true);
    setError('');
    try {
      const resp = await clawbotFetch(`/api/v1/trading/kline?symbol=${sym}&interval=${intv}&period=${prd}`);
      const data: KlineResponse = await resp.json();
      if (data.error) {
        setError(data.error);
        return [];
      }
      return data.data || [];
    } catch (e) {
      setError(e instanceof Error ? e.message : '获取数据失败');
      return [];
    } finally {
      setLoading(false);
    }
  };

  // 渲染图表
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // 清理旧图表
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#9ca3af',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: 'rgba(75, 85, 99, 0.15)' },
        horzLines: { color: 'rgba(75, 85, 99, 0.15)' },
      },
      crosshair: {
        mode: 0,
      },
      rightPriceScale: {
        borderColor: 'rgba(75, 85, 99, 0.3)',
      },
      timeScale: {
        borderColor: 'rgba(75, 85, 99, 0.3)',
        timeVisible: interval !== '1d' && interval !== '1wk',
      },
      width: chartContainerRef.current.clientWidth,
      height: 420,
    });

    chartRef.current = chart;

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#4ade80',
      downColor: '#ef4444',
      borderDownColor: '#ef4444',
      borderUpColor: '#4ade80',
      wickDownColor: '#ef4444',
      wickUpColor: '#4ade80',
    });

    // 成交量柱状图
    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#4ade8033',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    // 加载数据
    fetchKlineData(symbol, interval, period).then(data => {
      if (data.length > 0) {
        const candles: CandlestickData<Time>[] = data.map(d => ({
          time: d.time as Time,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
        }));
        candlestickSeries.setData(candles);

        const volumes = data.map(d => ({
          time: d.time as Time,
          value: d.volume,
          color: d.close >= d.open ? '#4ade8033' : '#ef444433',
        }));
        volumeSeries.setData(volumes);

        // 最新价格和涨跌幅
        const last = data[data.length - 1];
        const prev = data.length > 1 ? data[data.length - 2] : last;
        setLastPrice(last.close);
        setPriceChange(((last.close - prev.close) / prev.close) * 100);

        chart.timeScale().fitContent();
      }
    });

    // 响应式
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [symbol, interval, period]);

  const handleSearch = () => {
    const sym = inputValue.trim().toUpperCase();
    if (sym) setSymbol(sym);
  };

  return (
    <div className="space-y-4">
      {/* 搜索栏和控制按钮 */}
      <Card className="border-dark-600/50 bg-dark-800/40 backdrop-blur-sm">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* 标的搜索 */}
            <div className="flex items-center gap-2 flex-1 min-w-[200px]">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
                <input
                  type="text"
                  value={inputValue}
                  onChange={e => setInputValue(e.target.value.toUpperCase())}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                  placeholder="输入标的代码..."
                  className="w-full pl-9 pr-3 py-2 bg-dark-700/50 border border-dark-600/50 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-green-500/50"
                />
              </div>
              <button
                onClick={handleSearch}
                className="px-3 py-2 bg-green-500/20 hover:bg-green-500/30 border border-green-500/30 rounded-lg text-green-400 text-sm transition-colors"
              >
                查看
              </button>
            </div>

            {/* 快捷标的 */}
            <div className="flex flex-wrap gap-1.5">
              {DEFAULT_SYMBOLS.map(s => (
                <button
                  key={s}
                  onClick={() => { setInputValue(s); setSymbol(s); }}
                  className={`px-2.5 py-1 rounded-md text-xs transition-colors ${
                    symbol === s
                      ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                      : 'bg-dark-700/50 text-gray-400 hover:text-white border border-dark-600/50'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>

            {/* 分隔线 */}
            <div className="h-6 w-px bg-dark-600/50 hidden sm:block" />

            {/* 周期选择 */}
            <div className="flex gap-1.5">
              {INTERVALS.map(i => (
                <button
                  key={i.value}
                  onClick={() => setInterval(i.value)}
                  className={`px-2.5 py-1 rounded-md text-xs transition-colors ${
                    interval === i.value
                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                      : 'bg-dark-700/50 text-gray-400 hover:text-white border border-dark-600/50'
                  }`}
                >
                  {i.label}
                </button>
              ))}
            </div>

            {/* 时间范围 */}
            <div className="flex gap-1.5">
              {PERIODS.map(p => (
                <button
                  key={p.value}
                  onClick={() => setPeriod(p.value)}
                  className={`px-2.5 py-1 rounded-md text-xs transition-colors ${
                    period === p.value
                      ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                      : 'bg-dark-700/50 text-gray-400 hover:text-white border border-dark-600/50'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* K线图 */}
      <Card className="border-dark-600/50 bg-dark-800/40 backdrop-blur-sm">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-green-400" />
              {symbol}
              {lastPrice !== null && (
                <span className="text-base font-normal text-gray-300">
                  ${lastPrice.toFixed(2)}
                  <span className={`ml-2 text-sm ${priceChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                  </span>
                </span>
              )}
            </CardTitle>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
          </div>
        </CardHeader>
        <CardContent className="p-2">
          {error ? (
            <div className="flex items-center justify-center h-[420px] text-red-400 text-sm">
              {error}
            </div>
          ) : (
            <div ref={chartContainerRef} className="w-full" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
