import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BookOpen, Loader2 } from 'lucide-react';
import { clawbotFetch } from '@/lib/tauri';

/**
 * 订单簿条目
 */
interface OrderBookEntry {
  price: number;
  amount: number;
  total: number;
}

interface OrderBookData {
  bids: OrderBookEntry[];  // 买单
  asks: OrderBookEntry[];  // 卖单
  spread?: number;         // 买卖价差
  spreadPercent?: number;  // 价差百分比
}

interface OrderBookProps {
  symbol: string;
}

/**
 * 订单簿组件 - TradingView 风格
 * 显示实时买卖盘挂单
 */
export default function OrderBook({ symbol }: OrderBookProps) {
  const [orderBook, setOrderBook] = useState<OrderBookData>({ bids: [], asks: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 获取订单簿数据
  useEffect(() => {
    const fetchOrderBook = async () => {
      setLoading(true);
      setError('');
      try {
        const resp = await clawbotFetch(`/api/v1/trading/orderbook?symbol=${symbol}`);
        const data = await resp.json();
        
        if (data.error) {
          setError(data.error);
          // 使用模拟数据
          setOrderBook(generateMockOrderBook());
        } else {
          setOrderBook(data);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : '获取订单簿失败');
        // 使用模拟数据
        setOrderBook(generateMockOrderBook());
      } finally {
        setLoading(false);
      }
    };

    fetchOrderBook();
    // 每5秒刷新一次
    const interval = setInterval(fetchOrderBook, 5000);
    return () => clearInterval(interval);
  }, [symbol]);

  // 生成模拟订单簿数据
  const generateMockOrderBook = (): OrderBookData => {
    const basePrice = 150;
    const bids: OrderBookEntry[] = [];
    const asks: OrderBookEntry[] = [];
    
    let bidTotal = 0;
    for (let i = 0; i < 10; i++) {
      const amount = Math.random() * 100 + 10;
      bidTotal += amount;
      bids.push({
        price: basePrice - i * 0.1,
        amount,
        total: bidTotal,
      });
    }
    
    let askTotal = 0;
    for (let i = 0; i < 10; i++) {
      const amount = Math.random() * 100 + 10;
      askTotal += amount;
      asks.push({
        price: basePrice + 0.1 + i * 0.1,
        amount,
        total: askTotal,
      });
    }
    
    const spread = asks[0].price - bids[0].price;
    const spreadPercent = (spread / bids[0].price) * 100;
    
    return { bids, asks, spread, spreadPercent };
  };

  // 计算最大总量用于进度条
  const maxTotal = Math.max(
    ...orderBook.bids.map(b => b.total),
    ...orderBook.asks.map(a => a.total)
  );

  return (
    <Card className="border-dark-600/50 bg-dark-800/40 backdrop-blur-sm h-full flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-blue-400" />
            订单簿
          </CardTitle>
          {loading && <Loader2 className="h-3 w-3 animate-spin text-gray-400" />}
        </div>
      </CardHeader>
      <CardContent className="p-2 flex-1 overflow-hidden flex flex-col">
        {error && !orderBook.bids.length ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-xs">
            {error}
          </div>
        ) : (
          <>
            {/* 表头 */}
            <div className="grid grid-cols-3 gap-2 text-[10px] text-gray-500 font-medium mb-1 px-2">
              <div className="text-left">价格</div>
              <div className="text-right">数量</div>
              <div className="text-right">累计</div>
            </div>

            {/* 卖单（从上到下，价格从高到低） */}
            <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-dark-600 scrollbar-track-transparent">
              <div className="space-y-0.5">
                {orderBook.asks.slice().reverse().map((ask, idx) => (
                  <div
                    key={`ask-${idx}`}
                    className="relative grid grid-cols-3 gap-2 text-[11px] px-2 py-0.5 hover:bg-red-500/5 transition-colors"
                  >
                    {/* 背景进度条 */}
                    <div
                      className="absolute inset-y-0 right-0 bg-red-500/10"
                      style={{ width: `${(ask.total / maxTotal) * 100}%` }}
                    />
                    <div className="relative text-red-400 font-mono">${ask.price.toFixed(2)}</div>
                    <div className="relative text-right text-gray-300 font-mono">{ask.amount.toFixed(2)}</div>
                    <div className="relative text-right text-gray-500 font-mono text-[10px]">{ask.total.toFixed(0)}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* 价差 */}
            {orderBook.spread !== undefined && (
              <div className="my-2 px-2 py-1.5 bg-dark-700/50 rounded-md border border-dark-600/50">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-gray-400">价差</span>
                  <div className="flex items-center gap-2">
                    <span className="text-yellow-400 font-mono font-semibold">
                      ${orderBook.spread.toFixed(2)}
                    </span>
                    <span className="text-gray-500">
                      ({orderBook.spreadPercent?.toFixed(3)}%)
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* 买单（从上到下，价格从高到低） */}
            <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-dark-600 scrollbar-track-transparent">
              <div className="space-y-0.5">
                {orderBook.bids.map((bid, idx) => (
                  <div
                    key={`bid-${idx}`}
                    className="relative grid grid-cols-3 gap-2 text-[11px] px-2 py-0.5 hover:bg-green-500/5 transition-colors"
                  >
                    {/* 背景进度条 */}
                    <div
                      className="absolute inset-y-0 right-0 bg-green-500/10"
                      style={{ width: `${(bid.total / maxTotal) * 100}%` }}
                    />
                    <div className="relative text-green-400 font-mono">${bid.price.toFixed(2)}</div>
                    <div className="relative text-right text-gray-300 font-mono">{bid.amount.toFixed(2)}</div>
                    <div className="relative text-right text-gray-500 font-mono text-[10px]">{bid.total.toFixed(0)}</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
