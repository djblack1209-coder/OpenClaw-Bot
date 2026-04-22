import { AlertCircle, AlertTriangle, RefreshCw, Settings } from 'lucide-react';
import { motion } from 'framer-motion';
import { Button } from '../ui/button';
import type { FriendlyError } from '@/lib/errorMessages';
import { useLanguage } from '../../i18n';

interface ErrorStateProps {
  error: FriendlyError;
  onRetry?: () => void;
  onSettings?: () => void;
  compact?: boolean;  // for inline use in cards
}

export function ErrorState({ error, onRetry, onSettings, compact = false }: ErrorStateProps) {
  const { t } = useLanguage();
  if (compact) {
    return (
      <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--oc-danger)]/10 border border-[var(--oc-danger)]/20">
        <AlertCircle size={16} className="text-[var(--oc-danger)] flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white">{error.title}</p>
          {error.suggestion && <p className="text-xs text-gray-400 mt-0.5">{error.suggestion}</p>}
        </div>
        {error.retryable && onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw size={12} className="mr-1" />
            {t('shared.retry')}
          </Button>
        )}
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center py-12 px-6 text-center"
    >
      <div className="w-16 h-16 rounded-2xl bg-[var(--oc-danger)]/10 flex items-center justify-center mb-4">
        <AlertCircle size={32} className="text-[var(--oc-danger)]" />
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">{error.title}</h3>
      <p className="text-sm text-gray-400 mb-1 max-w-md">{error.message}</p>
      {error.suggestion && (
        <p className="text-sm text-gray-500 mb-6">{error.suggestion}</p>
      )}
      <div className="flex gap-3">
        {error.retryable && onRetry && (
          <Button variant="outline" onClick={onRetry}>
            <RefreshCw size={14} className="mr-2" />
            {t('shared.retry')}
          </Button>
        )}
        {onSettings && (
          <Button variant="outline" onClick={onSettings}>
            <Settings size={14} className="mr-2" />
            {t('shared.goToSettings')}
          </Button>
        )}
      </div>
    </motion.div>
  );
}

/** 简化版错误状态 — 用于各页面内联错误展示，接受纯字符串消息 */
interface SimpleErrorStateProps {
  /** 错误提示文字 */
  message?: string;
  /** 重试回调 */
  onRetry: () => void;
}

export function SimpleErrorState({ message, onRetry }: SimpleErrorStateProps) {
  const { t } = useLanguage();
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-8">
      <AlertTriangle size={20} style={{ color: 'var(--accent-red)' }} />
      <span className="font-mono text-xs" style={{ color: 'var(--accent-red)' }}>{message ?? t('common.error')}</span>
      <button
        onClick={onRetry}
        className="px-4 py-1.5 rounded-lg font-mono text-[11px] transition-all duration-200"
        style={{
          background: 'rgba(255, 0, 60, 0.1)',
          color: 'var(--accent-red)',
          border: '1px solid rgba(255, 0, 60, 0.25)',
        }}
      >
        <RefreshCw size={12} className="inline mr-1.5" />
        {t('common.retry')}
      </button>
    </div>
  );
}
