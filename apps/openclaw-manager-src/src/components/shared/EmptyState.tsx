/**
 * EmptyState — 通用空数据占位组件
 * 替代各页面中重复的 NoDataPlaceholder 实现
 * 支持自定义图标、标题、描述文字和操作按钮
 */
import { type LucideIcon, AlertCircle } from 'lucide-react';

interface EmptyStateProps {
  /** 展示的图标，默认为 AlertCircle */
  icon?: LucideIcon;
  /** 主标题文字 */
  title: string;
  /** 可选的描述文字（对应原 hint 参数） */
  description?: string;
  /** 可选的操作按钮 */
  action?: {
    label: string;
    onClick: () => void;
  };
  /** 额外的 CSS 类名 */
  className?: string;
}

export function EmptyState({
  icon: Icon = AlertCircle,
  title,
  description,
  action,
  className = '',
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center py-8 gap-2 ${className}`}
      style={{ color: 'var(--text-disabled)' }}
    >
      <Icon size={20} />
      <span className="font-mono text-xs text-center">{title}</span>
      {description && (
        <span
          className="font-mono text-[10px] text-center"
          style={{ color: 'var(--text-disabled)' }}
        >
          {description}
        </span>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-2 text-xs text-primary hover:underline"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
