import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';

interface AnimatedNumberProps {
  /** 目标数值 */
  value: number;
  /** 小数位数，默认 2 */
  decimals?: number;
  /** 前缀（如 "$" 或 "¥"） */
  prefix?: string;
  /** 后缀（如 "%" 或 "k"） */
  suffix?: string;
  /** 正值显示为绿色，负值红色 */
  colored?: boolean;
  /** 动画时长 ms，默认 500 */
  duration?: number;
  /** 额外 className */
  className?: string;
}

/**
 * 数字跳动动画组件 —— 用于盈亏金额、百分比等数字展示
 * 自动从当前值过渡到新值，支持颜色语义（正绿负红）
 */
export function AnimatedNumber({
  value,
  decimals = 2,
  prefix = '',
  suffix = '',
  colored = false,
  duration = 500,
  className,
}: AnimatedNumberProps) {
  const [display, setDisplay] = useState(value);
  const prevRef = useRef(value);
  const rafRef = useRef<number>();
  
  useEffect(() => {
    const from = prevRef.current;
    const to = value;
    const startTime = performance.now();
    
    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      /* 缓动函数：ease-out */
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = from + (to - from) * eased;
      setDisplay(current);
      
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        prevRef.current = to;
      }
    };
    
    rafRef.current = requestAnimationFrame(animate);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [value, duration]);
  
  const formatted = display.toFixed(decimals);
  const isPositive = value > 0;
  const isNegative = value < 0;
  
  return (
    <span
      className={clsx(
        'oc-tabular-nums',
        colored && isPositive && 'text-[var(--oc-success)]',
        colored && isNegative && 'text-[var(--oc-danger)]',
        className
      )}
    >
      {colored && isPositive && '+'}
      {prefix}{formatted}{suffix}
    </span>
  );
}
