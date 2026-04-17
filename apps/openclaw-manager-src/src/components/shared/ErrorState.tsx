import { AlertCircle, RefreshCw, Settings } from 'lucide-react';
import { motion } from 'framer-motion';
import { Button } from '../ui/button';
import type { FriendlyError } from '@/lib/errorMessages';

interface ErrorStateProps {
  error: FriendlyError;
  onRetry?: () => void;
  onSettings?: () => void;
  compact?: boolean;  // for inline use in cards
}

export function ErrorState({ error, onRetry, onSettings, compact = false }: ErrorStateProps) {
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
            重试
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
            重试
          </Button>
        )}
        {onSettings && (
          <Button variant="outline" onClick={onSettings}>
            <Settings size={14} className="mr-2" />
            前往设置
          </Button>
        )}
      </div>
    </motion.div>
  );
}
