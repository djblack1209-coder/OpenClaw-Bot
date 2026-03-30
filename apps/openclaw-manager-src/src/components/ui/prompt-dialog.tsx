import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

/**
 * 带文本输入的对话框组件
 * 用于替代浏览器原生 prompt()，提供统一的深色主题 UI
 */

interface PromptDialogProps {
  /** 是否显示对话框 */
  open: boolean;
  /** 关闭回调（取消或点击遮罩层） */
  onClose: () => void;
  /** 确认回调，传回用户输入的文本 */
  onConfirm: (value: string) => void;
  /** 对话框标题 */
  title: string;
  /** 对话框描述内容 */
  description?: string;
  /** 输入框占位符 */
  placeholder?: string;
  /** 输入框初始值 */
  defaultValue?: string;
  /** 确认按钮文字，默认"确认" */
  confirmText?: string;
  /** 取消按钮文字，默认"取消" */
  cancelText?: string;
}

export function PromptDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  placeholder = '',
  defaultValue = '',
  confirmText = '确认',
  cancelText = '取消',
}: PromptDialogProps) {
  const [value, setValue] = useState(defaultValue);
  const inputRef = useRef<HTMLInputElement>(null);

  // 每次打开时重置为 defaultValue 并聚焦
  useEffect(() => {
    if (open) {
      setValue(defaultValue);
      const timer = setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [open, defaultValue]);

  // ESC 键关闭
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onConfirm(trimmed);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={onClose}
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
              <p className="text-gray-400 text-sm mb-4 leading-relaxed">{description}</p>
            )}
            <input
              ref={inputRef}
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder={placeholder}
              className="w-full bg-dark-900 border border-dark-500 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-claw-500/50 focus:ring-1 focus:ring-claw-500/50 transition-all placeholder:text-gray-600 mb-5"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-300 bg-dark-700 hover:bg-dark-600 rounded-lg border border-dark-500 transition-colors"
              >
                {cancelText}
              </button>
              <button
                onClick={handleSubmit}
                disabled={!value.trim()}
                className="px-4 py-2 text-sm text-white bg-claw-600 hover:bg-claw-500 rounded-lg border border-claw-500/50 transition-colors disabled:opacity-50"
              >
                {confirmText}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
