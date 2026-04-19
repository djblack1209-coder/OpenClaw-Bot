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
        /* === shadcn 必需映射 === */
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
          /* Sonic Abyss 强调色 */
          red: '#ff003c',
          green: '#00ffaa',
          cyan: '#00d4ff',
          amber: '#fbbf24',
          purple: '#a78bfa',
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

        /* === Sonic Abyss 颜色系统 === */

        /* 兼容旧 claw-* 色（映射到 Killer Red） */
        claw: {
          50: '#1a0008',
          100: '#33000f',
          200: '#66001f',
          300: '#99002e',
          400: '#cc003e',
          500: '#ff003c',   // Killer Red
          600: '#ff3363',
          700: '#ff668a',
          800: '#ff99b1',
          900: '#ffccd8',
          950: '#ffe6ec',
        },

        /* dark-* 色阶（通过 CSS 变量） */
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

        /* 品牌色（从 tokens） */
        brand: designTokens.colors.brand,

        /* 语义色（从 tokens） */
        success: designTokens.colors.semantic.success,
        danger: designTokens.colors.semantic.danger,
        warning: designTokens.colors.semantic.warning,
        info: designTokens.colors.semantic.info,
      },

      fontFamily: {
        display: designTokens.typography.fontFamily.display,
        sans: designTokens.typography.fontFamily.sans,
        mono: designTokens.typography.fontFamily.mono,
      },
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
        /* Sonic Abyss 发光阴影 */
        'glow-red': '0 0 30px rgba(255, 0, 60, 0.4)',
        'glow-cyan': '0 0 30px rgba(0, 212, 255, 0.4)',
        'glow-green': '0 0 30px rgba(0, 255, 170, 0.4)',
        'glow-claw': '0 0 30px rgba(255, 0, 60, 0.3)',
        'inner-light': 'inset 0 1px 0 0 rgba(255, 255, 255, 0.03)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'fade-in': 'fadeIn 0.2s ease-out',
        'pulse-glow': 'pulseGlow 2s infinite cubic-bezier(0.4, 0, 0.2, 1)',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(0, 212, 255, 0.4)' },
          '100%': { boxShadow: '0 0 20px rgba(0, 212, 255, 0.7)' },
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
        pulseGlow: {
          '0%': { transform: 'scale(0.5)', opacity: '1' },
          '100%': { transform: 'scale(2.5)', opacity: '0' },
        },
      },
      backdropBlur: {
        xs: '2px',
        glass: '24px',
      },
      zIndex: designTokens.zIndex,
    },
  },
  plugins: [require("tailwindcss-animate")],
}
