import { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Brain, Shield, DollarSign, Zap, Loader2,
} from 'lucide-react';
import { api } from '../../lib/tauri';

interface OmegaStatus {
  omega?: boolean;
  brain?: { active_tasks: number; pending_callbacks: number };
  event_bus?: { total_events: number; subscription_count: number };
  cost?: { today_spend: number; daily_budget: number; budget_used_pct: number; over_budget: boolean };
  security?: { admin_count: number; pin_configured: boolean };
  self_heal?: { total_attempts: number; healed: number; heal_rate: string };
  executor?: { execution_stats: Record<string, number> };
}

export function OmegaStatusPanel() {
  const [status, setStatus] = useState<OmegaStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.omegaStatus();
      setStatus(data);
      setError('');
    } catch (e: unknown) {
      setError(e?.toString() || 'API 不可达');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (error) {
    return (
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-zinc-400">
            <Brain size={14} className="text-amber-400" />
            OMEGA Brain
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-zinc-500">未连接 — 启动 ClawBot 后可用</p>
        </CardContent>
      </Card>
    );
  }

  if (!status) return null;

  const cost = status.cost;
  const brain = status.brain;
  const eventBus = status.event_bus;
  const selfHeal = status.self_heal;
  const costPct = cost?.budget_used_pct || 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {/* Brain 状态 */}
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardHeader className="pb-1 pt-3 px-3">
          <CardTitle className="text-xs flex items-center gap-1.5 text-zinc-400">
            <Brain size={12} className="text-amber-400" />
            Brain
            {loading && <Loader2 size={10} className="animate-spin ml-auto text-zinc-600" />}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-3 pb-3">
          <div className="text-lg font-bold text-amber-400">
            {brain?.active_tasks || 0}
          </div>
          <p className="text-[10px] text-zinc-500">活跃任务</p>
          <p className="text-[10px] text-zinc-600 mt-0.5">
            {eventBus?.total_events || 0} 事件 / {eventBus?.subscription_count || 0} 订阅
          </p>
        </CardContent>
      </Card>

      {/* 成本控制 */}
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardHeader className="pb-1 pt-3 px-3">
          <CardTitle className="text-xs flex items-center gap-1.5 text-zinc-400">
            <DollarSign size={12} className="text-green-400" />
            今日费用
          </CardTitle>
        </CardHeader>
        <CardContent className="px-3 pb-3">
          <div className="text-lg font-bold text-green-400">
            ${(cost?.today_spend || 0).toFixed(4)}
          </div>
          <div className="mt-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                costPct > 80 ? 'bg-red-500' : costPct > 50 ? 'bg-yellow-500' : 'bg-green-500'
              }`}
              style={{ width: `${Math.min(costPct, 100)}%` }}
            />
          </div>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            {costPct.toFixed(1)}% / ${cost?.daily_budget || 50}
          </p>
        </CardContent>
      </Card>

      {/* 自愈引擎 */}
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardHeader className="pb-1 pt-3 px-3">
          <CardTitle className="text-xs flex items-center gap-1.5 text-zinc-400">
            <Zap size={12} className="text-blue-400" />
            自愈引擎
          </CardTitle>
        </CardHeader>
        <CardContent className="px-3 pb-3">
          <div className="text-lg font-bold text-blue-400">
            {selfHeal?.heal_rate || 'N/A'}
          </div>
          <p className="text-[10px] text-zinc-500">
            {selfHeal?.healed || 0} / {selfHeal?.total_attempts || 0} 已修复
          </p>
        </CardContent>
      </Card>

      {/* 安全门控 */}
      <Card className="border-zinc-800 bg-zinc-900/60">
        <CardHeader className="pb-1 pt-3 px-3">
          <CardTitle className="text-xs flex items-center gap-1.5 text-zinc-400">
            <Shield size={12} className="text-purple-400" />
            安全
          </CardTitle>
        </CardHeader>
        <CardContent className="px-3 pb-3">
          <div className="text-lg font-bold text-purple-400">
            {status.security?.pin_configured ? '🔒' : '🔓'}
          </div>
          <p className="text-[10px] text-zinc-500">
            {status.security?.admin_count || 0} 管理员
          </p>
          <p className="text-[10px] text-zinc-600">
            PIN {status.security?.pin_configured ? '已设置' : '未设置'}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
