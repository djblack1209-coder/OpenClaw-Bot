import { useEffect, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

/**
 * 通用确认对话框组件
 * 用于替代浏览器原生 confirm() 和 alert()，提供统一的深色主题 UI
 */

interface ConfirmDialogProps {
  /** 是否显示对话框 */
  open: boolean;
  /** 关闭回调（取消或点击遮罩层） */
  onClose: () => void;
  /** 确认回调 */
  onConfirm: () => void;
  /** 对话框标题 */
  title: string;
  /** 对话框描述内容 */
  description?: string;
  /** 确认按钮文字，默认"确认" */
  confirmText?: string;
  /** 取消按钮文字，默认"取消" */
  cancelText?: string;
  /** 确认按钮是否为危险样式（红色），默认 false */
  destructive?: boolean;
  /** 确认操作进行中（显示加载状态） */
  loading?: boolean;
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = '确认',
  cancelText = '取消',
  destructive = false,
  loading = false,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  // 打开时自动聚焦确认按钮
  useEffect(() => {
    if (open) {
      // 延迟聚焦，等待动画开始后
      const timer = setTimeout(() => confirmRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
  }, [open]);

  // ESC 键关闭
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, loading, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={() => !loading && onClose()}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: 0.15 }}
            className="bg-dark-800 border border-dark-600 rounded-xl shadow-2xl p-6 w-full max-w-sm mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-white font-semibold text-base mb-2">{title}</h3>
            {description && (
              <p className="text-gray-400 text-sm mb-5 leading-relaxed">{description}</p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={onClose}
                disabled={loading}
                className="px-4 py-2 text-sm text-gray-300 bg-dark-700 hover:bg-dark-600 rounded-lg border border-dark-500 transition-colors disabled:opacity-50"
              >
                {cancelText}
              </button>
              <button
                ref={confirmRef}
                onClick={onConfirm}
                disabled={loading}
                className={`px-4 py-2 text-sm text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2 ${
                  destructive
                    ? 'bg-red-600 hover:bg-red-500 border border-red-500/50'
                    : 'bg-claw-600 hover:bg-claw-500 border border-claw-500/50'
                }`}
              >
                {loading && (
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                )}
                {confirmText}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
