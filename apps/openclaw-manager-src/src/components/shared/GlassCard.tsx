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
 * Abyss 玻璃卡片组件 — Sonic Abyss 设计系统的核心容器
 * 玻璃态背景 + 24px 圆角 + 光扫 hover 效果
 * 同时导出为 GlassCard（兼容旧引用）和 AbyssCard（新名称）
 */
export function GlassCard({ children, className, hoverable = true, onClick }: GlassCardProps) {
  return (
    <motion.div
      className={clsx(
        'abyss-card p-5',
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

/* 新名称别名 — 推荐在新代码中使用 AbyssCard */
export const AbyssCard = GlassCard;
