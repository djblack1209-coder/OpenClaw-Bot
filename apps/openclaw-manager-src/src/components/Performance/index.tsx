import { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, Gauge, Activity, Loader2, Clock, Zap } from 'lucide-react';
import clsx from 'clsx';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { clawbotFetchJson } from '@/lib/tauri-core';
import { createLogger } from '@/lib/logger';
import { toast } from 'sonner';

const perfLogger = createLogger('Performance');

/** 单个指标的统计数据 */
interface MetricStats {
  count: number;
  avg: number;
  p50: number;
  p95: number;
  max: number;
  min: number;
}

/** 性能数据响应结构 */
interface PerfData {
  metrics: Record<string, MetricStats>;
  report: string;
}

/** 指标中文名称映射 */
const METRIC_LABELS: Record<string, { name: string; icon: React.ElementType }> = {
  'bot.handle_message': { name: '消息处理', icon: Activity },
  'brain.process_message': { name: '大脑决策', icon: Zap },
  'trader.run_cycle': { name: '交易周期', icon: Clock },
  'llm.acompletion': { name: 'LLM 调用', icon: Gauge },
};

/** 展示顺序 */
const METRIC_ORDER = [
  'bot.handle_message',
  'brain.process_message',
  'trader.run_cycle',
  'llm.acompletion',
];

/** 根据平均耗时返回颜色类 */
function getAvgColor(avg: number): string {
  if (avg < 1) return 'text-green-400';
  if (avg <= 5) return 'text-yellow-400';
  return 'text-red-400';
}

/** 格式化秒数为友好显示 */
function formatSeconds(val: number): string {
  if (val < 0.01) return '<0.01s';
  return `${val.toFixed(2)}s`;
}

export function Performance() {
  const [data, setData] = useState<PerfData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** 拉取性能数据 */
  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      const result = await clawbotFetchJson('/api/v1/perf') as PerfData;
      setData(result);
      perfLogger.info('性能数据获取成功');
    } catch (err) {
      perfLogger.error('性能数据获取失败', err);
      if (!silent) {
        toast.error('获取性能数据失败，请检查后端是否运行');
      }
      setData(null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  /* 首次加载 */
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* 自动刷新控制 */
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => fetchData(true), 10000);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [autoRefresh, fetchData]);

  /** 判断是否有有效数据（至少一个指标有调用记录） */
  const hasData =
    data?.metrics &&
    Object.values(data.metrics).some((m) => m.count > 0);

  /** 按顺序获取指标列表（已知的排前面，未知的追加） */
  const orderedKeys = (() => {
    if (!data?.metrics) return [];
    const known = METRIC_ORDER.filter((k) => k in data.metrics);
    const unknown = Object.keys(data.metrics).filter((k) => !METRIC_ORDER.includes(k));
    return [...known, ...unknown];
  })();

  return (
    <div className="h-full flex flex-col gap-5 overflow-y-auto scroll-container">
      {/* ── 顶部工具栏 ── */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <Gauge size={20} className="text-[var(--brand-500)]" />
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">性能指标</h2>
        </div>
        <div className="flex items-center gap-3">
          {/* 自动刷新开关 */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <span className="text-xs text-[var(--text-tertiary)]">自动刷新</span>
            <button
              onClick={() => setAutoRefresh((v) => !v)}
              className={clsx(
                'relative w-9 h-5 rounded-full transition-colors duration-200',
                autoRefresh ? 'bg-[var(--brand-500)]' : 'bg-[var(--bg-tertiary)]'
              )}
            >
              <span
                className={clsx(
                  'absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform duration-200',
                  autoRefresh && 'translate-x-4'
                )}
              />
            </button>
          </label>
          {/* 手动刷新 */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchData(false)}
            disabled={refreshing}
          >
            {refreshing ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            <span className="ml-1">刷新</span>
          </Button>
        </div>
      </div>

      {/* ── 加载中 ── */}
      {loading && (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--brand-500)]" />
        </div>
      )}

      {/* ── 无数据状态 ── */}
      {!loading && !hasData && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-3">
            <Gauge size={48} className="mx-auto text-[var(--text-disabled)]" />
            <p className="text-[var(--text-secondary)] text-sm">
              暂无性能数据。启动 ClawBot 后端后，数据将自动采集。
            </p>
          </div>
        </div>
      )}

      {/* ── 有数据时展示 ── */}
      {!loading && hasData && data && (
        <>
          {/* 摘要卡片行 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 flex-shrink-0">
            {orderedKeys.map((key) => {
              const metric = data.metrics[key];
              if (!metric || metric.count === 0) return null;
              const meta = METRIC_LABELS[key] || { name: key, icon: Activity };
              const Icon = meta.icon;
              return (
                <Card key={key} className="bg-[var(--bg-secondary)] border-[var(--border-default)]">
                  <CardContent className="pt-1">
                    <div className="flex items-center gap-2 mb-2">
                      <Icon size={16} className="text-[var(--text-tertiary)]" />
                      <span className="text-xs font-medium text-[var(--text-secondary)] truncate">
                        {meta.name}
                      </span>
                    </div>
                    {/* 平均耗时 - 大数字 */}
                    <div className={clsx('text-2xl font-bold tabular-nums', getAvgColor(metric.avg))}>
                      {formatSeconds(metric.avg)}
                    </div>
                    {/* 次要指标 */}
                    <div className="flex items-center justify-between mt-2 text-xs text-[var(--text-tertiary)]">
                      <span>调用 {metric.count} 次</span>
                      <span>P95 {formatSeconds(metric.p95)}</span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* 详细数据表 */}
          <Card className="bg-[var(--bg-secondary)] border-[var(--border-default)] flex-shrink-0">
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[var(--border-default)]">
                      <th className="text-left py-2.5 px-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                        指标
                      </th>
                      <th className="text-right py-2.5 px-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                        调用次数
                      </th>
                      <th className="text-right py-2.5 px-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                        平均耗时
                      </th>
                      <th className="text-right py-2.5 px-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                        P50
                      </th>
                      <th className="text-right py-2.5 px-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                        P95
                      </th>
                      <th className="text-right py-2.5 px-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                        最大值
                      </th>
                      <th className="text-right py-2.5 px-3 text-xs font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                        最小值
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {orderedKeys.map((key) => {
                      const metric = data.metrics[key];
                      if (!metric || metric.count === 0) return null;
                      const meta = METRIC_LABELS[key] || { name: key, icon: Activity };
                      return (
                        <tr
                          key={key}
                          className="border-b border-[var(--border-light)] last:border-0 hover:bg-[var(--bg-tertiary)] transition-colors"
                        >
                          <td className="py-2.5 px-3 font-medium text-[var(--text-primary)]">
                            {meta.name}
                            <span className="ml-2 text-xs text-[var(--text-disabled)]">{key}</span>
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-[var(--text-secondary)]">
                            {metric.count}
                          </td>
                          <td className={clsx('py-2.5 px-3 text-right tabular-nums font-medium', getAvgColor(metric.avg))}>
                            {formatSeconds(metric.avg)}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-[var(--text-secondary)]">
                            {formatSeconds(metric.p50)}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-[var(--text-secondary)]">
                            {formatSeconds(metric.p95)}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-[var(--text-secondary)]">
                            {formatSeconds(metric.max)}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-[var(--text-secondary)]">
                            {formatSeconds(metric.min)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
