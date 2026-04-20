/**
 * i18n 国际化系统
 * 基于 React Context 实现，支持 zh-CN / en-US 切换
 * 翻译存储在 localStorage，key 为 'openclaw-language'
 */
import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from 'react';
import { zhCN } from './zh-CN';
import { enUS } from './en-US';

/* ====== 类型定义 ====== */
export type Language = 'zh-CN' | 'en-US';

interface LanguageContextValue {
  /** 当前语言 */
  lang: Language;
  /** 切换语言（同时写入 localStorage） */
  setLang: (lang: Language) => void;
  /** 翻译函数：传入 key 返回对应文本，找不到则返回 key 本身 */
  t: (key: string) => string;
}

/* ====== 翻译表映射 ====== */
const translations: Record<Language, Record<string, string>> = {
  'zh-CN': zhCN,
  'en-US': enUS,
};

/* ====== localStorage key ====== */
const STORAGE_KEY = 'openclaw-language';

/** 从 localStorage 读取语言偏好，默认 zh-CN */
function getStoredLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'zh-CN' || stored === 'en-US') return stored;
  } catch {
    // localStorage 不可用时静默降级
  }
  return 'zh-CN';
}

/* ====== Context ====== */
const LanguageContext = createContext<LanguageContextValue | null>(null);

/* ====== Provider 组件 ====== */
interface LanguageProviderProps {
  children: ReactNode;
}

export function LanguageProvider({ children }: LanguageProviderProps) {
  const [lang, setLangState] = useState<Language>(getStoredLanguage);

  /** 切换语言并持久化到 localStorage */
  const setLang = useCallback((newLang: Language) => {
    setLangState(newLang);
    try {
      localStorage.setItem(STORAGE_KEY, newLang);
    } catch {
      // localStorage 不可用时静默降级
    }
  }, []);

  /** 翻译函数：查找当前语言的翻译表，找不到返回 key 本身 */
  const t = useCallback((key: string): string => {
    return translations[lang][key] ?? key;
  }, [lang]);

  const value = useMemo<LanguageContextValue>(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

/* ====== Hook ====== */

/** 获取 i18n 上下文：{ lang, setLang, t } */
export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error('useLanguage 必须在 LanguageProvider 内部使用');
  }
  return ctx;
}
