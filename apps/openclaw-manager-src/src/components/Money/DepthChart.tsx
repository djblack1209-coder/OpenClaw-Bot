import { useEffect, useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Layers, Loader2, AlertCircle } from 'lucide-react';
import { clawbotFetch } from '@/lib/tauri';

/**
 * 深度图数据格式
 */
interface DepthDataPoint {
  price: number;
  amount: number;
  total: number;
}

interface DepthData {
  bids: DepthDataPoint[];  // 买单（绿色）
  asks: DepthDataPoint[];  // 卖单（红色）
}

interface DepthChartProps {
  symbol: string;
}

/**
 * 深度图组件 - TradingView 风格
 * 审计修复: 移除 Mock 数据，API 失败时展示空态
 */
export default function DepthChart({ symbol }: DepthChartProps) {
  const [depthData, setDepthData] = useState<DepthData>({ bids: [], asks: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 获取深度数据
  useEffect(() => {
    const fetchDepth = async () => {
      setLoading(true);
      setError('');
      try {
        const resp = await clawbotFetch(`/api/v1/trading/depth?symbol=${symbol}`);
        const data = await resp.json();
        
        if (data.error) {
          setError(data.error);
        } else {
          setDepthData(data);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '获取深度数据失败');
      } finally {
        setLoading(false);
      }
    };

    fetchDepth();
    // 每10秒刷新一次
    const interval = setInterval(fetchDepth, 10000);
    return () => clearInterval(interval);
  }, [symbol]);

  // 合并买卖盘数据用于图表展示
  const chartData = [
    ...depthData.bids.map(d => ({ price: d.price, bid: d.total, ask: 0 })),
    ...depthData.asks.map(d => ({ price: d.price, bid: 0, ask: d.total })),
  ].sort((a, b) => a.price - b.price);

  return (
    <Card className="border-dark-600/50 bg-dark-800/40 backdrop-blur-sm h-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <Layers className="h-4 w-4 text-purple-400" />
            市场深度
          </CardTitle>
          {loading && <Loader2 className="h-3 w-3 animate-spin text-gray-400" />}
        </div>
      </CardHeader>
      <CardContent className="p-2">
        {error && !depthData.bids.length ? (
          <div className="flex flex-col items-center justify-center h-[200px] text-center">
            <AlertCircle className="h-6 w-6 text-gray-500 mb-2" />
            <p className="text-gray-500 text-xs">{error}</p>
            <p className="text-gray-600 text-xs mt-1">深度数据暂不可用</p>
          </div>
        ) : depthData.bids.length === 0 && depthData.asks.length === 0 && !loading ? (
          <div className="flex flex-col items-center justify-center h-[200px] text-center">
            <Layers className="h-6 w-6 text-gray-500 mb-2" />
            <p className="text-gray-500 text-xs">暂无深度数据</p>
          </div>
        ) : (
          <div className="h-[200px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="colorBid" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4ade80" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#4ade80" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorAsk" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2e2e33" vertical={false} />
                <XAxis 
                  dataKey="price" 
                  stroke="#52525b" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false}
                  tickFormatter={(val) => `$${val.toFixed(1)}`}
                />
                <YAxis 
                  stroke="#52525b" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false}
                  tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#1a1a1d', 
                    borderColor: '#3d3d44', 
                    color: '#fff', 
                    borderRadius: '8px',
                    fontSize: '11px',
                  }}
                  formatter={(value, name) => {
                    const val = typeof value === 'number' ? value : 0;
                    return [
                      `${val.toFixed(0)}`,
                      name === 'bid' ? '买盘' : '卖盘'
                    ];
                  }}
                  labelFormatter={(label) => `价格: $${label}`}
                />
                <Area 
                  type="stepAfter" 
                  dataKey="bid" 
                  stroke="#4ade80" 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#colorBid)" 
                />
                <Area 
                  type="stepAfter" 
                  dataKey="ask" 
                  stroke="#ef4444" 
                  strokeWidth={2}
                  fillOpacity={1} 
                  fill="url(#colorAsk)" 
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
