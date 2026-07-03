import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import prettierConfig from 'eslint-config-prettier';

export default tseslint.config(
  // Base JS recommended rules
  js.configs.recommended,

  // TypeScript recommended (type-aware rules intentionally excluded to keep linting fast)
  ...tseslint.configs.recommended,

  // React
  {
    plugins: {
      react: reactPlugin,
      'react-hooks': reactHooksPlugin,
    },
    settings: {
      react: { version: '18.3' },
    },
    rules: {
      // React runtime (react-jsx) doesn't need React in scope
      'react/react-in-jsx-scope': 'off',
      'react/jsx-uses-react': 'off',

      // Core React rules that catch real bugs
      'react/jsx-key': 'warn',
      'react/jsx-no-duplicate-props': 'error',
      'react/jsx-no-undef': 'error',
      'react/no-children-prop': 'warn',
      'react/no-danger-with-children': 'error',
      'react/no-direct-mutation-state': 'error',
      'react/no-unescaped-entities': 'warn',

      // Hooks rules — these prevent subtle bugs
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
    },
  },

  // TypeScript-specific rule overrides
  {
    rules: {
      // Relax noisy TS rules that aren't real bugs
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          destructuredArrayIgnorePattern: '^_',
        },
      ],
      // 现有 API/Tauri 边界大量接收后端动态 JSON；先把 any 作为迁移型类型债保留，
      // 避免与 npm 脚本的 --max-warnings 0 互相打架，后续按模块逐步收紧具体类型。
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/no-require-imports': 'off',
    },
  },

  // Node 静态测试脚本
  {
    files: ['src/**/*.test.mjs'],
    languageOptions: {
      globals: {
        process: 'readonly',
      },
    },
  },

  // Prettier — disables formatting rules that conflict
  prettierConfig,

  // Global ignores
  {
    ignores: ['dist/', 'node_modules/', 'src-tauri/', '*.config.js', '*.config.ts'],
  },
);
