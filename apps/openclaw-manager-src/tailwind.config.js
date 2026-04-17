import { designTokens } from './src/styles/tokens';

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        card: {
          DEFAULT: 'var(--card)',
          foreground: 'var(--card-foreground)'
        },
        popover: {
          DEFAULT: 'var(--popover)',
          foreground: 'var(--popover-foreground)'
        },
        primary: {
          DEFAULT: 'var(--primary)',
          foreground: 'var(--primary-foreground)'
        },
        secondary: {
          DEFAULT: 'var(--secondary)',
          foreground: 'var(--secondary-foreground)'
        },
        muted: {
          DEFAULT: 'var(--muted)',
          foreground: 'var(--muted-foreground)'
        },
        accent: {
          DEFAULT: 'var(--accent)',
          foreground: 'var(--accent-foreground)',
          cyan: '#22d3ee',
          purple: '#a78bfa',
          green: '#4ade80',
          amber: '#fbbf24',
        },
        destructive: {
          DEFAULT: 'var(--destructive)',
          foreground: 'var(--destructive-foreground)'
        },
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        chart: {
          '1': 'var(--chart-1)',
          '2': 'var(--chart-2)',
          '3': 'var(--chart-3)',
          '4': 'var(--chart-4)',
          '5': 'var(--chart-5)'
        },
        sidebar: {
          DEFAULT: 'var(--sidebar)',
          foreground: 'var(--sidebar-foreground)',
          primary: 'var(--sidebar-primary)',
          'primary-foreground': 'var(--sidebar-primary-foreground)',
          accent: 'var(--sidebar-accent)',
          'accent-foreground': 'var(--sidebar-accent-foreground)',
          border: 'var(--sidebar-border)',
          ring: 'var(--sidebar-ring)'
        },
        // OpenClaw 品牌色（保留兼容性）
        claw: {
          50: '#fef3f2',
          100: '#fee4e2',
          200: '#ffccc7',
          300: '#ffa8a0',
          400: '#ff7a6b',
          500: '#f94d3a',
          600: '#e63024',
          700: '#c1241a',
          800: '#a02119',
          900: '#84221c',
          950: '#480d09',
        },
        // 深色主题背景（通过 CSS 变量实现浅色/深色模式切换）
        dark: {
          950: 'var(--dark-950)',
          900: 'var(--dark-900)',
          800: 'var(--dark-800)',
          700: 'var(--dark-700)',
          600: 'var(--dark-600)',
          500: 'var(--dark-500)',
          400: 'var(--dark-400)',
          300: 'var(--dark-300)',
          200: 'var(--dark-200)',
          100: 'var(--dark-100)',
        },
        // Design Tokens - 品牌色（青色系）
        brand: designTokens.colors.brand,
        // Design Tokens - 语义色
        success: designTokens.colors.semantic.success,
        danger: designTokens.colors.semantic.danger,
        warning: designTokens.colors.semantic.warning,
        info: designTokens.colors.semantic.info,
      },
      fontFamily: designTokens.typography.fontFamily,
      fontSize: designTokens.typography.fontSize,
      fontWeight: designTokens.typography.fontWeight,
      spacing: designTokens.spacing,
      borderRadius: {
        ...designTokens.borderRadius,
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      boxShadow: {
        ...designTokens.boxShadow,
        'glow-claw': '0 0 30px rgba(249, 77, 58, 0.3)',
        'glow-cyan': '0 0 30px rgba(34, 211, 238, 0.3)',
        'glow-green': '0 0 30px rgba(74, 222, 128, 0.3)',
        'inner-light': 'inset 0 1px 0 0 rgba(255, 255, 255, 0.05)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'fade-in': 'fadeIn 0.2s ease-out',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(249, 77, 58, 0.5)' },
          '100%': { boxShadow: '0 0 20px rgba(249, 77, 58, 0.8)' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
      zIndex: designTokens.zIndex,
    },
  },
  plugins: [require("tailwindcss-animate")],
}
