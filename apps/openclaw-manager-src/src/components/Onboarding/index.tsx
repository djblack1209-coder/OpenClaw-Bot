import { useState, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Check, ChevronLeft, ChevronRight, Eye, EyeOff,
  Zap, TrendingUp, Share2, Bot, Shield,
} from 'lucide-react';
import { api } from '@/lib/tauri';
import { useLanguage } from '@/i18n';
import { toast } from '@/lib/notify';

/* ────────────────────────────────────────────────────────────────
   Types
──────────────────────────────────────────────────────────────── */

/** 功能列表的 i18n key 映射 */
const FEATURE_KEYS: { id: string; labelKey: string; descKey: string; icon: typeof Zap; color: string; alwaysOn?: boolean }[] = [
  { id: 'xianyu', labelKey: 'onboarding.feature.xianyuLabel', descKey: 'onboarding.feature.xianyuDesc', icon: Zap, color: 'var(--accent-amber)' },
  { id: 'trading', labelKey: 'onboarding.feature.tradingLabel', descKey: 'onboarding.feature.tradingDesc', icon: TrendingUp, color: 'var(--accent-green)' },
  { id: 'social', labelKey: 'onboarding.feature.socialLabel', descKey: 'onboarding.feature.socialDesc', icon: Share2, color: 'var(--accent-cyan)' },
  { id: 'assistant', labelKey: 'onboarding.feature.assistantLabel', descKey: 'onboarding.feature.assistantDesc', icon: Bot, color: 'var(--accent-purple)', alwaysOn: true },
];

/* ────────────────────────────────────────────────────────────────
   Slide direction helper
──────────────────────────────────────────────────────────────── */

const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 300 : -300,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction: number) => ({
    x: direction > 0 ? -300 : 300,
    opacity: 0,
  }),
};

/* ────────────────────────────────────────────────────────────────
   Ambient particles (替代 Confetti — Sonic Abyss 风格微粒)
──────────────────────────────────────────────────────────────── */

function AmbientParticles() {
  const particles = useMemo(
    () =>
      Array.from({ length: 20 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        delay: Math.random() * 2,
        duration: 3 + Math.random() * 3,
        size: 2 + Math.random() * 3,
        opacity: 0.1 + Math.random() * 0.2,
      })),
    [],
  );

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {particles.map((p) => (
        <motion.div
          key={p.id}
          initial={{ y: '100%', x: `${p.x}%`, opacity: 0 }}
          animate={{
            y: '-10%',
            opacity: [0, p.opacity, 0],
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            repeat: Infinity,
            ease: 'linear',
          }}
          style={{
            position: 'absolute',
            width: p.size,
            height: p.size,
            borderRadius: '50%',
            background: 'var(--accent-cyan)',
          }}
        />
      ))}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Step 1: Welcome — Sonic Abyss 风格
──────────────────────────────────────────────────────────────── */

function StepWelcome({ onNext }: { onNext: () => void }) {
  const { t } = useLanguage();
  const featureCards = [
    { icon: Zap, titleKey: 'onboarding.welcome.aiCS', descKey: 'onboarding.welcome.aiCSDesc', color: 'var(--accent-amber)' },
    { icon: TrendingUp, titleKey: 'onboarding.welcome.quantTrading', descKey: 'onboarding.welcome.quantTradingDesc', color: 'var(--accent-green)' },
    { icon: Share2, titleKey: 'onboarding.welcome.socialOps', descKey: 'onboarding.welcome.socialOpsDesc', color: 'var(--accent-cyan)' },
  ];
  return (
    <div className="flex flex-col items-center text-center max-w-md mx-auto">
      {/* Logo — 用渐变圆形图标替代 emoji */}
      <motion.div
        initial={{ scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 200, damping: 15 }}
        className="w-20 h-20 rounded-2xl flex items-center justify-center mb-6"
        style={{
          background: 'linear-gradient(135deg, rgba(0,255,136,0.15), rgba(0,200,255,0.15))',
          border: '1px solid rgba(0,255,136,0.2)',
          boxShadow: '0 0 40px rgba(0,255,136,0.1)',
        }}
      >
        <Shield size={36} style={{ color: 'var(--accent-green)' }} />
      </motion.div>
      <h1 className="font-display text-3xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>{t('onboarding.welcome.title')}</h1>
      <p className="font-mono text-sm mb-8" style={{ color: 'var(--text-secondary)' }}>{t('onboarding.welcome.subtitle')}</p>

      <div className="grid grid-cols-1 gap-3 w-full mb-8">
        {featureCards.map((feat) => (
          <motion.div
            key={feat.titleKey}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: featureCards.indexOf(feat) * 0.1 + 0.2 }}
            className="flex items-center gap-3 p-3 rounded-xl"
            style={{
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                 style={{ background: `${feat.color}15`, border: `1px solid ${feat.color}30` }}>
              <feat.icon size={18} style={{ color: feat.color }} />
            </div>
            <div className="text-left">
              <div className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{t(feat.titleKey)}</div>
              <div className="font-mono text-[11px]" style={{ color: 'var(--text-disabled)' }}>{t(feat.descKey)}</div>
            </div>
          </motion.div>
        ))}
      </div>

      <button
        onClick={onNext}
        className="w-full px-5 py-3 rounded-xl font-display text-sm font-bold transition-all flex items-center justify-center gap-2"
        style={{
          background: 'var(--accent-cyan)',
          color: '#000',
        }}
      >
        {t('onboarding.welcome.startSetup')}
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Step 2: Feature Selection — Sonic Abyss 风格
──────────────────────────────────────────────────────────────── */

function StepFeatures({
  selected,
  onToggle,
}: {
  selected: Set<string>;
  onToggle: (id: string) => void;
}) {
  const { t } = useLanguage();
  return (
    <div className="max-w-lg mx-auto">
      <h2 className="font-display text-2xl font-bold text-center mb-2" style={{ color: 'var(--text-primary)' }}>{t('onboarding.features.title')}</h2>
      <p className="font-mono text-sm text-center mb-6" style={{ color: 'var(--text-secondary)' }}>{t('onboarding.features.subtitle')}</p>

      <div className="grid grid-cols-1 gap-3">
        {FEATURE_KEYS.map((feat) => {
          const isSelected = selected.has(feat.id);
          const IconComp = feat.icon;
          return (
            <motion.div
              key={feat.id}
              whileHover={{ scale: feat.alwaysOn ? 1 : 1.02 }}
              whileTap={{ scale: feat.alwaysOn ? 1 : 0.98 }}
              className={`p-4 rounded-xl cursor-pointer transition-all ${feat.alwaysOn ? 'opacity-70' : ''}`}
              style={{
                background: isSelected ? 'rgba(255,255,255,0.05)' : 'rgba(255,255,255,0.02)',
                border: `1px solid ${isSelected ? feat.color + '50' : 'rgba(255,255,255,0.06)'}`,
                boxShadow: isSelected ? `0 0 20px ${feat.color}10` : 'none',
              }}
              onClick={() => !feat.alwaysOn && onToggle(feat.id)}
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
                     style={{ background: `${feat.color}15`, border: `1px solid ${feat.color}30` }}>
                  <IconComp size={20} style={{ color: feat.color }} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-display text-sm font-bold" style={{ color: 'var(--text-primary)' }}>{t(feat.labelKey)}</h3>
                    {feat.alwaysOn && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-mono"
                            style={{ background: `${feat.color}20`, color: feat.color }}>
                        {t('onboarding.features.alwaysOn')}
                      </span>
                    )}
                  </div>
                  <p className="font-mono text-[11px] mt-0.5" style={{ color: 'var(--text-disabled)' }}>{t(feat.descKey)}</p>
                </div>
                <div
                  className="w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors shrink-0"
                  style={{
                    background: isSelected ? feat.color : 'transparent',
                    borderColor: isSelected ? feat.color : 'rgba(255,255,255,0.2)',
                  }}
                >
                  {isSelected && <Check size={14} className="text-black" />}
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Step 3: API Key Config — Sonic Abyss 风格
──────────────────────────────────────────────────────────────── */

function StepAPIConfig({
  apiKey,
  setApiKey,
  baseUrl,
  setBaseUrl,
}: {
  apiKey: string;
  setApiKey: (v: string) => void;
  baseUrl: string;
  setBaseUrl: (v: string) => void;
}) {
  const [showKey, setShowKey] = useState(false);
  const { t } = useLanguage();

  const inputStyle: React.CSSProperties = {
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.1)',
    color: 'var(--text-primary)',
    borderRadius: 12,
    padding: '10px 14px',
    outline: 'none',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
  };

  return (
    <div className="max-w-lg mx-auto">
      <h2 className="font-display text-2xl font-bold text-center mb-2" style={{ color: 'var(--text-primary)' }}>{t('onboarding.apiConfig.title')}</h2>
      <p className="font-mono text-sm text-center mb-6" style={{ color: 'var(--text-secondary)' }}>{t('onboarding.apiConfig.subtitle')}</p>

      <div className="space-y-4">
        <div>
          <label className="block font-mono text-xs mb-1.5" style={{ color: 'var(--text-disabled)' }}>{t('onboarding.apiConfig.apiKeyLabel')}</label>
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full pr-10"
              style={inputStyle}
            />
            <button
              type="button"
              className="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
              style={{ color: 'var(--text-disabled)' }}
              onClick={() => setShowKey(!showKey)}
            >
              {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        <div>
          <label className="block font-mono text-xs mb-1.5" style={{ color: 'var(--text-disabled)' }}>{t('onboarding.apiConfig.baseUrlLabel')}</label>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            className="w-full"
            style={inputStyle}
          />
        </div>

        <p className="font-mono text-[10px] text-center mt-4" style={{ color: 'var(--text-disabled)' }}>
          {t('onboarding.apiConfig.hint')}
        </p>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Step 4: Completion — Sonic Abyss 风格
──────────────────────────────────────────────────────────────── */

function StepComplete({
  selectedFeatures,
  onFinish,
}: {
  selectedFeatures: Set<string>;
  onFinish: () => void;
}) {
  const { t } = useLanguage();
  const selectedLabels = FEATURE_KEYS.filter((f) => selectedFeatures.has(f.id));

  return (
    <div className="relative flex flex-col items-center text-center max-w-md mx-auto">
      <AmbientParticles />

      {/* 完成图标 — 渐变圆形 + Check */}
      <motion.div
        initial={{ scale: 0, rotate: -180 }}
        animate={{ scale: 1, rotate: 0 }}
        transition={{ type: 'spring', stiffness: 200, damping: 12 }}
        className="w-20 h-20 rounded-2xl flex items-center justify-center mb-6"
        style={{
          background: 'linear-gradient(135deg, rgba(0,255,136,0.2), rgba(0,200,100,0.1))',
          border: '1px solid rgba(0,255,136,0.3)',
          boxShadow: '0 0 40px rgba(0,255,136,0.15)',
        }}
      >
        <Check size={36} style={{ color: 'var(--accent-green)' }} />
      </motion.div>

      <h2 className="font-display text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>{t('onboarding.complete.title')}</h2>
      <p className="font-mono text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>{t('onboarding.complete.subtitle')}</p>

      <div className="flex flex-wrap gap-2 justify-center mb-8">
        {selectedLabels.map((feat) => {
          const IconComp = feat.icon;
          return (
            <motion.span
              key={feat.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 + selectedLabels.indexOf(feat) * 0.1 }}
              className="px-3 py-1.5 rounded-lg font-mono text-xs font-medium flex items-center gap-1.5"
              style={{
                background: `${feat.color}15`,
                color: feat.color,
                border: `1px solid ${feat.color}30`,
              }}
            >
              <IconComp size={12} />
              {t(feat.labelKey)}
            </motion.span>
          );
        })}
      </div>

      <button
        onClick={onFinish}
        className="w-full px-5 py-3 rounded-xl font-display text-sm font-bold transition-all flex items-center justify-center gap-2"
        style={{
          background: 'var(--accent-cyan)',
          color: '#000',
        }}
      >
        {t('onboarding.complete.enterConsole')}
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Main Onboarding Component
──────────────────────────────────────────────────────────────── */

const TOTAL_STEPS = 4;

export function Onboarding({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);
  const { t } = useLanguage();

  // Step 2 state — feature selection
  const [selectedFeatures, setSelectedFeatures] = useState<Set<string>>(
    new Set(['assistant']), // AI助手 always on
  );

  // Step 3 state — API config
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');

  const goNext = useCallback(() => {
    if (step < TOTAL_STEPS - 1) {
      setDirection(1);
      setStep((s) => s + 1);
    }
  }, [step]);

  const goBack = useCallback(() => {
    if (step > 0) {
      setDirection(-1);
      setStep((s) => s - 1);
    }
  }, [step]);

  const toggleFeature = useCallback((id: string) => {
    setSelectedFeatures((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      // Always keep assistant
      next.add('assistant');
      return next;
    });
  }, []);

  const handleFinish = useCallback(async () => {
    // Persist onboarding state
    localStorage.setItem('openclaw-onboarding-complete', 'true');
    localStorage.setItem(
      'openclaw-onboarding-features',
      JSON.stringify(Array.from(selectedFeatures)),
    );

    // 保存 API 配置（如果用户填写了）
    if (apiKey.trim()) {
      try {
        await api.saveEnvValue('LLM_API_KEY', apiKey.trim());
      } catch {
        // 提示用户保存失败，但不阻止完成引导
        toast.error(t('onboarding.apiKeySaveFailed'), { channel: 'notification' });
      }
    }
    if (baseUrl.trim()) {
      try {
        await api.saveEnvValue('LLM_BASE_URL', baseUrl.trim());
      } catch {
        toast.error(t('onboarding.baseUrlSaveFailed'), { channel: 'notification' });
      }
    }

    onComplete();
  }, [selectedFeatures, apiKey, baseUrl, onComplete, t]);

  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={{ background: 'var(--bg-primary, #020202)' }}>
      {/* 背景装饰 — Sonic Abyss 风格 */}
      <div className="fixed inset-0 pointer-events-none" style={{
        background: 'radial-gradient(ellipse at 50% 20%, rgba(0,200,255,0.04) 0%, transparent 50%)',
      }} />

      {/* macOS 拖拽区 */}
      <div className="h-12 flex-shrink-0" data-tauri-drag-region="" />

      {/* 进度条 + 跳过按钮 */}
      <div className="relative z-10 px-8 mb-6">
        <div className="max-w-lg mx-auto flex items-center gap-2">
          {Array.from({ length: TOTAL_STEPS }, (_, i) => (
            <div key={i} className="flex-1 h-[2px] rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
              <motion.div
                className="h-full rounded-full"
                style={{ background: 'var(--accent-cyan)' }}
                initial={false}
                animate={{ width: i <= step ? '100%' : '0%' }}
                transition={{ duration: 0.3 }}
              />
            </div>
          ))}
          {/* 跳过按钮 */}
          {step < TOTAL_STEPS - 1 && (
            <button
              onClick={handleFinish}
              className="ml-2 font-mono text-[10px] transition-colors whitespace-nowrap"
              style={{ color: 'var(--text-disabled)' }}
              aria-label={t('onboarding.skipGuide')}
            >
              {t('onboarding.skip')}
            </button>
          )}
        </div>
      </div>

      {/* 步骤内容 */}
      <div className="relative z-10 flex-1 flex items-center justify-center px-8 overflow-hidden">
        <AnimatePresence mode="wait" custom={direction}>
          <motion.div
            key={step}
            custom={direction}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className="w-full"
          >
            {step === 0 && <StepWelcome onNext={goNext} />}
            {step === 1 && (
              <StepFeatures selected={selectedFeatures} onToggle={toggleFeature} />
            )}
            {step === 2 && (
              <StepAPIConfig
                apiKey={apiKey}
                setApiKey={setApiKey}
                baseUrl={baseUrl}
                setBaseUrl={setBaseUrl}
              />
            )}
            {step === 3 && (
              <StepComplete selectedFeatures={selectedFeatures} onFinish={handleFinish} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* 底部导航 — Sonic Abyss 风格 */}
      <div className="relative z-10 px-8 pb-8">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          {step > 0 && step < TOTAL_STEPS - 1 ? (
            <button
              onClick={goBack}
              className="px-4 py-2 rounded-lg font-mono text-xs transition-all flex items-center gap-1"
              style={{
                background: 'rgba(255,255,255,0.04)',
                color: 'var(--text-secondary)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <ChevronLeft size={14} />
              {t('onboarding.prevStep')}
            </button>
          ) : (
            <div />
          )}
          {step > 0 && step < TOTAL_STEPS - 1 && (
            <button
              onClick={goNext}
              className="px-5 py-2 rounded-lg font-display text-sm font-bold transition-all flex items-center gap-1"
              style={{
                background: 'var(--accent-cyan)',
                color: '#000',
              }}
            >
              {t('onboarding.nextStep')}
              <ChevronRight size={14} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
