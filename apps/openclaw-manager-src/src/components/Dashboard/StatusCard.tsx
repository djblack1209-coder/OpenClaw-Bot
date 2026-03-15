import { Activity, Cpu, HardDrive, Clock } from 'lucide-react';
import clsx from 'clsx';

interface ServiceStatus {
  running: boolean;
  pid: number | null;
  port: number;
  uptime_seconds: number | null;
  memory_mb: number | null;
  cpu_percent: number | null;
}

interface StatusCardProps {
  status: ServiceStatus | null;
  loading: boolean;
}

export function StatusCard({ status, loading }: StatusCardProps) {
  const formatUptime = (seconds: number | null) => {
    if (!seconds) return '--';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  return (
    <div className="bg-dark-700 rounded-2xl p-6 border border-dark-500">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-lg font-semibold text-white">服务状态</h3>
        <div className="flex items-center gap-2">
          <div
            className={clsx(
              'status-dot',
              loading ? 'warning' : status?.running ? 'running' : 'stopped'
            )}
          />
          <span
            className={clsx(
              'text-sm font-medium',
              loading
                ? 'text-yellow-400'
                : status?.running
                ? 'text-green-400'
                : 'text-red-400'
            )}
          >
            {loading ? '检测中...' : status?.running ? '运行中' : '已停止'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-dark-600 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity size={16} className="text-accent-cyan" />
            <span className="text-xs text-gray-400">端口</span>
          </div>
          <p className="text-xl font-semibold text-white">
            {status?.port || 18789}
          </p>
        </div>

        <div className="bg-dark-600 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Cpu size={16} className="text-accent-purple" />
            <span className="text-xs text-gray-400">进程 ID</span>
          </div>
          <p className="text-xl font-semibold text-white">
            {status?.pid || '--'}
          </p>
        </div>

        <div className="bg-dark-600 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <HardDrive size={16} className="text-accent-green" />
            <span className="text-xs text-gray-400">内存</span>
          </div>
          <p className="text-xl font-semibold text-white">
            {status?.memory_mb ? `${status.memory_mb.toFixed(1)} MB` : '--'}
          </p>
        </div>

        <div className="bg-dark-600 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Clock size={16} className="text-accent-amber" />
            <span className="text-xs text-gray-400">运行时间</span>
          </div>
          <p className="text-xl font-semibold text-white">
            {formatUptime(status?.uptime_seconds || null)}
          </p>
        </div>
      </div>
    </div>
  );
}
