import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Wallet, Loader2 } from 'lucide-react';
import { api, isTauri } from '@/lib/tauri';

/**
 * 资产分布数据
 */
interface AssetItem {
  name: string;
  value: number;
  color: string;
}

/**
 * 资产分布饼图组件 - TradingView 风格
 */
export function AssetDistribution() {
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalValue, setTotalValue] = useState(0);

  useEffect(() => {
    const fetchAssets = async () => {
      if (!isTauri()) {
        setLoading(false);
        // 使用模拟数据
        const mockData: AssetItem[] = [
          { name: '股票', value: 45000, color: '#00D4FF' },
          { name: '加密货币', value: 28000, color: '#4ADE80' },
          { name: '现金', value: 15000, color: '#FBBF24' },
          { name: '其他', value: 12000, color: '#9CA3AF' },
        ];
        setAssets(mockData);
        setTotalValue(mockData.reduce((sum, item) => sum + item.value, 0));
        return;
      }

      try {
        const resp = await api.clawbotTradingSystem();
        const data = resp as { assets?: AssetItem[]; total?: number };
        
        if (data.assets && data.assets.length > 0) {
          setAssets(data.assets);
          setTotalValue(data.total || data.assets.reduce((sum, item) => sum + item.value, 0));
        } else {
          // 使用模拟数据
          const mockData: AssetItem[] = [
            { name: '股票', value: 45000, color: '#00D4FF' },
            { name: '加密货币', value: 28000, color: '#4ADE80' },
            { name: '现金', value: 15000, color: '#FBBF24' },
            { name: '其他', value: 12000, color: '#9CA3AF' },
          ];
          setAssets(mockData);
          setTotalValue(mockData.reduce((sum, item) => sum + item.value, 0));
        }
      } catch (e) {
        // 使用模拟数据
        const mockData: AssetItem[] = [
          { name: '股票', value: 45000, color: '#00D4FF' },
          { name: '加密货币', value: 28000, color: '#4ADE80' },
          { name: '现金', value: 15000, color: '#FBBF24' },
          { name: '其他', value: 12000, color: '#9CA3AF' },
        ];
        setAssets(mockData);
        setTotalValue(mockData.reduce((sum, item) => sum + item.value, 0));
      } finally {
        setLoading(false);
      }
    };

    fetchAssets();
  }, []);

  return (
    <Card className="border-[var(--border-default)] bg-[var(--bg-primary)] shadow-lg h-full">
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Wallet className="h-4 w-4 text-[var(--brand-500)]" />
          资产分布
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4">
        {loading ? (
          <div className="flex items-center justify-center h-[280px]">
            <Loader2 className="h-8 w-8 animate-spin text-[var(--brand-500)]" />
          </div>
        ) : (
          <>
            {/* 总资产 */}
            <div className="text-center mb-4">
              <p className="text-xs text-[var(--text-secondary)] mb-1">总资产</p>
              <p className="text-2xl font-bold text-[var(--text-primary)] oc-tabular-nums">
                ${totalValue.toLocaleString()}
              </p>
            </div>

            {/* 饼图 */}
            <div className="h-[200px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={assets}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {assets.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--bg-elevated)',
                      border: '1px solid var(--border-default)',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                    formatter={(value) => {
                      const val = typeof value === 'number' ? value : 0;
                      return [`$${val.toLocaleString()}`, ''];
                    }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    iconType="circle"
                    iconSize={8}
                    formatter={(value) => (
                      <span className="text-xs text-[var(--text-secondary)]">{value}</span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>

            {/* 资产列表 */}
            <div className="mt-4 space-y-2">
              {assets.map((asset, index) => {
                const percentage = ((asset.value / totalValue) * 100).toFixed(1);
                return (
                  <div key={index} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <div
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: asset.color }}
                      />
                      <span className="text-[var(--text-secondary)]">{asset.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[var(--text-primary)] font-medium oc-tabular-nums">
                        ${asset.value.toLocaleString()}
                      </span>
                      <span className="text-[var(--text-tertiary)] oc-tabular-nums">
                        {percentage}%
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
