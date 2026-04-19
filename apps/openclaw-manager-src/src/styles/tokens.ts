/**
 * Sonic Abyss 设计系统 - Design Tokens
 *
 * 设计规范：纯黑暗终端美学
 * 主色调：#00d4ff (Hacker Cyan) + #ff003c (Killer Red) + #00ffaa (Hacker Green)
 * 背景：#020202 纯黑
 */

export const designTokens = {
  // ===== 颜色系统 =====
  colors: {
    // 品牌色（青色系）
    brand: {
      DEFAULT: '#00d4ff',
      50: '#002933',
      100: '#005266',
      200: '#007a99',
      300: '#00a3cc',
      400: '#00d4ff',
      500: '#00d4ff',  // 主色
      600: '#33dfff',
      700: '#66e8ff',
      800: '#99f0ff',
      900: '#ccf7ff',
    },

    // 强调色
    accent: {
      red: '#ff003c',       // Killer Red — 危险/亏损
      green: '#00ffaa',     // Hacker Green — 成功/盈利
      cyan: '#00d4ff',      // Hacker Cyan — 主色/链接
      amber: '#fbbf24',     // 警告
      purple: '#a78bfa',    // 辅助
    },

    // 语义色（映射到强调色）
    semantic: {
      success: '#00ffaa',    // 绿色 — 成功/涨
      danger: '#ff003c',     // 红色 — 危险/跌
      warning: '#fbbf24',    // 黄色 — 警告
      info: '#00d4ff',       // 青色 — 信息
    },

    // 深色背景系统
    background: {
      base: '#020202',         // 最底层背景
      elevated: '#0a0a0d',     // 提升层
      card: 'rgba(15, 15, 18, 0.4)',       // 卡片背景（玻璃态）
      cardHover: 'rgba(25, 25, 30, 0.5)',  // 卡片 hover
    },

    // 文字颜色
    text: {
      primary: '#ffffff',                    // 主文字
      secondary: 'rgba(255, 255, 255, 0.55)', // 次要文字
      tertiary: 'rgba(255, 255, 255, 0.35)',  // 三级文字
      disabled: 'rgba(255, 255, 255, 0.2)',   // 禁用文字
    },

    // 玻璃边框
    glass: {
      border: 'rgba(255, 255, 255, 0.08)',
      borderHover: 'rgba(255, 255, 255, 0.15)',
    },

    // 边框颜色（兼容旧格式）
    border: {
      DEFAULT: 'rgba(255, 255, 255, 0.08)',
      light: 'rgba(255, 255, 255, 0.04)',
      medium: 'rgba(255, 255, 255, 0.12)',
      strong: 'rgba(255, 255, 255, 0.18)',
    },

    // 交易相关颜色
    trading: {
      buy: '#00ffaa',          // 买入/做多（Hacker Green）
      sell: '#ff003c',         // 卖出/做空（Killer Red）
      neutral: 'rgba(255, 255, 255, 0.4)', // 中性
    },

    // 发光效果
    glow: {
      red: 'rgba(255, 0, 60, 0.4)',
      green: 'rgba(0, 255, 170, 0.4)',
      cyan: 'rgba(0, 212, 255, 0.4)',
    },
  },

  // ===== 字体系统 =====
  typography: {
    fontFamily: {
      display: [
        'Space Grotesk',
        'system-ui',
        'sans-serif',
      ],
      sans: [
        'Inter',
        'system-ui',
        'sans-serif',
      ],
      mono: [
        'JetBrains Mono',
        'SF Mono',
        'Fira Code',
        'monospace',
      ],
    },
    fontSize: {
      xs: ['0.75rem', { lineHeight: '1rem' }],      // 12px
      sm: ['0.875rem', { lineHeight: '1.25rem' }],   // 14px
      base: ['1rem', { lineHeight: '1.5rem' }],       // 16px
      lg: ['1.125rem', { lineHeight: '1.75rem' }],    // 18px
      xl: ['1.25rem', { lineHeight: '1.75rem' }],     // 20px
      '2xl': ['1.5rem', { lineHeight: '2rem' }],      // 24px
      '3xl': ['1.875rem', { lineHeight: '2.25rem' }], // 30px
      '4xl': ['2.25rem', { lineHeight: '2.5rem' }],   // 36px
    },
    fontWeight: {
      light: '300',
      normal: '400',
      medium: '500',
      bold: '700',
      black: '900',
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
    sm: '0.5rem',     // 8px
    DEFAULT: '0.75rem', // 12px
    md: '1rem',        // 16px
    lg: '1.5rem',      // 24px — 玻璃卡片
    xl: '2rem',        // 32px — 大圆角卡片
    full: '9999px',
  },

  // ===== 阴影系统 =====
  boxShadow: {
    sm: '0 1px 2px 0 rgba(0, 0, 0, 0.3)',
    DEFAULT: '0 2px 8px rgba(0, 0, 0, 0.4)',
    md: '0 4px 12px rgba(0, 0, 0, 0.5)',
    lg: '0 8px 24px rgba(0, 0, 0, 0.6)',
    xl: '0 12px 32px rgba(0, 0, 0, 0.7)',
    '2xl': '0 16px 48px rgba(0, 0, 0, 0.8)',
    glow: '0 0 20px rgba(0, 212, 255, 0.3)',
    glowStrong: '0 0 30px rgba(0, 212, 255, 0.5)',
    glowRed: '0 0 30px rgba(255, 0, 60, 0.4)',
    glowGreen: '0 0 30px rgba(0, 255, 170, 0.4)',
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
      bounce: 'cubic-bezier(0.16, 1, 0.3, 1)',
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
