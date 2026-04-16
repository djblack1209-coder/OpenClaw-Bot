import clsx from 'clsx';

type StatusType = 'running' | 'stopped' | 'error' | 'warning' | 'starting' | 'stopping';

interface StatusIndicatorProps {
  status: StatusType;
  /** 状态文本标签 */
  label?: string;
  /** 尺寸：sm(6px) / md(8px) / lg(10px) */
  size?: 'sm' | 'md' | 'lg';
}

/** 状态文本映射 */
const statusLabels: Record<StatusType, string> = {
  running: '运行中',
  stopped: '已停止',
  error: '异常',
  warning: '警告',
  starting: '启动中',
  stopping: '停止中',
};

/** 状态颜色映射 */
const statusColors: Record<StatusType, string> = {
  running: 'bg-[var(--oc-success)]',
  stopped: 'bg-gray-400 dark:bg-gray-600',
  error: 'bg-[var(--oc-danger)]',
  warning: 'bg-[var(--oc-warning)]',
  starting: 'bg-[var(--oc-brand)]',
  stopping: 'bg-orange-400',
};

/** 带发光效果的状态 */
const glowStatuses = new Set<StatusType>(['running', 'error']);

/** 尺寸映射 */
const sizeMap = { sm: 'w-1.5 h-1.5', md: 'w-2 h-2', lg: 'w-2.5 h-2.5' };

/**
 * 状态指示器 —— 圆点 + 可选文本标签
 * 支持 6 种状态，运行中和异常状态带发光脉冲动画
 */
export function StatusIndicator({ status, label, size = 'md' }: StatusIndicatorProps) {
  const displayLabel = label ?? statusLabels[status];
  const hasGlow = glowStatuses.has(status);
  const isAnimating = status === 'starting' || status === 'stopping';
  
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="relative flex">
        {/* 发光脉冲外圈 */}
        {hasGlow && (
          <span
            className={clsx(
              'absolute inset-0 rounded-full animate-ping opacity-75',
              statusColors[status]
            )}
          />
        )}
        {/* 核心圆点 */}
        <span
          className={clsx(
            'relative rounded-full',
            sizeMap[size],
            statusColors[status],
            isAnimating && 'animate-pulse'
          )}
        />
      </span>
      {displayLabel && (
        <span className={clsx(
          'text-xs font-medium',
          status === 'running' && 'text-[var(--oc-success)]',
          status === 'stopped' && 'text-gray-400',
          status === 'error' && 'text-[var(--oc-danger)]',
          status === 'warning' && 'text-[var(--oc-warning)]',
          (status === 'starting' || status === 'stopping') && 'text-[var(--oc-brand)]',
        )}>
          {displayLabel}
        </span>
      )}
    </span>
  );
}
