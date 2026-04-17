/**
 * OpenClaw Design System - Design Tokens
 * 
 * 设计规范：深色主题 + TradingView 风格
 * 主色调：#00D4FF (青色) + #0D0F14 (深色背景)
 */

export const designTokens = {
  // ===== 颜色系统 =====
  colors: {
    // 品牌色（青色系）
    brand: {
      DEFAULT: '#00D4FF',
      50: '#E5F9FF',
      100: '#CCF3FF',
      200: '#99E7FF',
      300: '#66DBFF',
      400: '#33CFFF',
      500: '#00D4FF',  // 主色
      600: '#00A3CC',
      700: '#007A99',
      800: '#005266',
      900: '#002933',
    },
    
    // 语义色
    semantic: {
      success: '#4ADE80',    // 绿色 - 成功/涨
      danger: '#EF4444',     // 红色 - 危险/跌
      warning: '#FBBF24',    // 黄色 - 警告
      info: '#60A5FA',       // 蓝色 - 信息
    },
    
    // 深色背景系统
    background: {
      primary: '#0D0F14',    // 主背景
      secondary: '#1A1A1D',  // 次级背景
      tertiary: '#242428',   // 三级背景
      elevated: '#2E2E33',   // 悬浮层背景
    },
    
    // 文字颜色
    text: {
      primary: '#FFFFFF',    // 主文字
      secondary: '#9CA3AF',  // 次要文字
      tertiary: '#6B7280',   // 三级文字
      disabled: '#4B5563',   // 禁用文字
      inverse: '#0D0F14',    // 反色文字（浅色背景上）
    },
    
    // 边框颜色
    border: {
      DEFAULT: 'rgba(255, 255, 255, 0.1)',
      light: 'rgba(255, 255, 255, 0.05)',
      medium: 'rgba(255, 255, 255, 0.15)',
      strong: 'rgba(255, 255, 255, 0.2)',
    },
    
    // 交易相关颜色
    trading: {
      buy: '#4ADE80',        // 买入/做多
      sell: '#EF4444',       // 卖出/做空
      neutral: '#9CA3AF',    // 中性
    },
  },
  
  // ===== 字体系统 =====
  typography: {
    fontFamily: {
      sans: [
        'SF Pro Display',
        '-apple-system',
        'BlinkMacSystemFont',
        'PingFang SC',
        'Hiragino Sans GB',
        'Microsoft YaHei',
        'sans-serif',
      ],
      mono: [
        'SF Mono',
        'JetBrains Mono',
        'Fira Code',
        'Menlo',
        'monospace',
      ],
    },
    fontSize: {
      xs: ['0.75rem', { lineHeight: '1rem' }],      // 12px
      sm: ['0.875rem', { lineHeight: '1.25rem' }],  // 14px
      base: ['1rem', { lineHeight: '1.5rem' }],     // 16px
      lg: ['1.125rem', { lineHeight: '1.75rem' }],  // 18px
      xl: ['1.25rem', { lineHeight: '1.75rem' }],   // 20px
      '2xl': ['1.5rem', { lineHeight: '2rem' }],    // 24px
      '3xl': ['1.875rem', { lineHeight: '2.25rem' }], // 30px
      '4xl': ['2.25rem', { lineHeight: '2.5rem' }], // 36px
    },
    fontWeight: {
      normal: '400',
      medium: '500',
      semibold: '600',
      bold: '700',
    },
  },
  
  // ===== 间距系统 =====
  spacing: {
    0: '0',
    1: '0.25rem',   // 4px
    2: '0.5rem',    // 8px
    3: '0.75rem',   // 12px
    4: '1rem',      // 16px
    5: '1.25rem',   // 20px
    6: '1.5rem',    // 24px
    8: '2rem',      // 32px
    10: '2.5rem',   // 40px
    12: '3rem',     // 48px
    16: '4rem',     // 64px
    20: '5rem',     // 80px
    24: '6rem',     // 96px
  },
  
  // ===== 圆角系统 =====
  borderRadius: {
    none: '0',
    sm: '0.25rem',   // 4px
    DEFAULT: '0.5rem',   // 8px
    md: '0.625rem',  // 10px
    lg: '0.75rem',   // 12px
    xl: '1rem',      // 16px
    '2xl': '1.5rem', // 24px
    full: '9999px',
  },
  
  // ===== 阴影系统 =====
  boxShadow: {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
    DEFAULT: '0 2px 8px rgba(0, 0, 0, 0.1)',
    md: '0 4px 12px rgba(0, 0, 0, 0.15)',
    lg: '0 8px 24px rgba(0, 0, 0, 0.2)',
    xl: '0 12px 32px rgba(0, 0, 0, 0.25)',
    '2xl': '0 16px 48px rgba(0, 0, 0, 0.3)',
    glow: '0 0 20px rgba(0, 212, 255, 0.3)',
    glowStrong: '0 0 30px rgba(0, 212, 255, 0.5)',
  },
  
  // ===== 动画系统 =====
  animation: {
    duration: {
      fast: '150ms',
      normal: '200ms',
      slow: '300ms',
      slower: '500ms',
    },
    easing: {
      easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
      easeOut: 'cubic-bezier(0, 0, 0.2, 1)',
      easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
    },
  },
  
  // ===== Z-Index 系统 =====
  zIndex: {
    base: 0,
    dropdown: 1000,
    sticky: 1020,
    fixed: 1030,
    modalBackdrop: 1040,
    modal: 1050,
    popover: 1060,
    tooltip: 1070,
  },
};

export default designTokens;
