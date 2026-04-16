import { motion } from 'framer-motion';
import clsx from 'clsx';

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  /** 是否启用 hover 上浮效果，默认 true */
  hoverable?: boolean;
  /** 点击回调 */
  onClick?: () => void;
}

/**
 * 毛玻璃卡片组件 —— C 端所有卡片的基础容器
 * 带有毛玻璃背景、圆角、阴影和可选的 hover 上浮动画
 */
export function GlassCard({ children, className, hoverable = true, onClick }: GlassCardProps) {
  return (
    <motion.div
      className={clsx(
        'oc-glass-card p-5',
        hoverable && 'cursor-default',
        onClick && 'cursor-pointer',
        className
      )}
      whileHover={hoverable ? { y: -2 } : undefined}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      onClick={onClick}
    >
      {children}
    </motion.div>
  );
}
