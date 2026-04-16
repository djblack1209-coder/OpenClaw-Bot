import { motion } from 'framer-motion';
import clsx from 'clsx';

interface ToggleSwitchProps {
  /** 当前开关状态 */
  checked: boolean;
  /** 状态变化回调 */
  onChange: (checked: boolean) => void;
  /** 是否禁用 */
  disabled?: boolean;
  /** 尺寸：sm / md / lg */
  size?: 'sm' | 'md' | 'lg';
  /** 额外 className */
  className?: string;
}

/* 尺寸配置 */
const sizeConfig = {
  sm: { track: 'w-8 h-5', thumb: 'w-3.5 h-3.5', translate: 14 },
  md: { track: 'w-11 h-6', thumb: 'w-5 h-5', translate: 20 },
  lg: { track: 'w-14 h-8', thumb: 'w-6 h-6', translate: 24 },
};

/**
 * iOS 风格拨动开关 —— 带弹性动画
 * 用于自动交易、服务启停等需要醒目开关的场景
 */
export function ToggleSwitch({
  checked,
  onChange,
  disabled = false,
  size = 'md',
  className,
}: ToggleSwitchProps) {
  const config = sizeConfig[size];
  
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={clsx(
        'relative inline-flex items-center rounded-full transition-colors duration-200',
        config.track,
        checked ? 'bg-[var(--oc-success)]' : 'bg-gray-300 dark:bg-gray-600',
        disabled && 'opacity-50 cursor-not-allowed',
        !disabled && 'cursor-pointer',
        className
      )}
    >
      <motion.span
        className={clsx(
          'absolute left-0.5 rounded-full bg-white shadow-md',
          config.thumb
        )}
        animate={{ x: checked ? config.translate : 0 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
      />
    </button>
  );
}
