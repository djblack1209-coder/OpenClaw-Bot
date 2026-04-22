import { Loader2 } from 'lucide-react';
import { useLanguage } from '../../i18n';

/** 统一的加载状态组件 — 居中旋转图标 + 可选提示文字 */
interface LoadingStateProps {
  /** 加载提示文字，默认使用 i18n 的 common.loading */
  message?: string;
}

export function LoadingState({ message }: LoadingStateProps) {
  const { t } = useLanguage();
  return (
    <div className="flex items-center justify-center gap-2 py-8">
      <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
      <span className="font-mono text-xs" style={{ color: 'var(--text-tertiary)' }}>{message ?? t('common.loading')}</span>
    </div>
  );
}
