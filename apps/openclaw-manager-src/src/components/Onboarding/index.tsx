import { useState, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { GlassCard } from '../shared';
import { Button } from '../ui/button';
import { Check, ChevronLeft, ChevronRight, Eye, EyeOff } from 'lucide-react';
import { api } from '@/lib/tauri';

/* ────────────────────────────────────────────────────────────────
   Types
──────────────────────────────────────────────────────────────── */

interface FeatureOption {
  id: string;
  label: string;
  description: string;
  emoji: string;
  alwaysOn?: boolean;
}

const FEATURES: FeatureOption[] = [
  { id: 'xianyu', label: '闲鱼AI客服', description: '自动回复买家消息，智能议价与成交', emoji: '🐟' },
  { id: 'trading', label: '自动交易', description: '量化策略执行，自动化投资组合管理', emoji: '📈' },
  { id: 'social', label: '社媒运营', description: '多平台内容自动生成与定时发布', emoji: '📱' },
  { id: 'assistant', label: 'AI助手', description: '你的私人智能助手，随时待命', emoji: '🤖', alwaysOn: true },
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
   Confetti animation (pure CSS, no deps)
──────────────────────────────────────────────────────────────── */

function ConfettiEffect() {
  const particles = useMemo(
    () =>
      Array.from({ length: 30 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        delay: Math.random() * 0.8,
        duration: 1.5 + Math.random() * 1.5,
        color: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#FF9FF3'][
          i % 7
        ],
        size: 4 + Math.random() * 6,
      })),
    [],
  );

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {particles.map((p) => (
        <motion.div
          key={p.id}
          initial={{ y: -20, x: `${p.x}%`, opacity: 1, scale: 1, rotate: 0 }}
          animate={{
            y: '120%',
            opacity: [1, 1, 0],
            scale: [1, 0.8, 0.4],
            rotate: Math.random() > 0.5 ? 360 : -360,
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            ease: 'easeIn',
          }}
          style={{
            position: 'absolute',
            width: p.size,
            height: p.size,
            borderRadius: Math.random() > 0.5 ? '50%' : '2px',
            backgroundColor: p.color,
          }}
        />
      ))}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Step 1: Welcome
──────────────────────────────────────────────────────────────── */

function StepWelcome({ onNext }: { onNext: () => void }) {
  return (
    <div className="flex flex-col items-center text-center max-w-md mx-auto">
      <motion.div
        initial={{ scale: 0.5, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 200, damping: 15 }}
        className="text-8xl mb-6"
      >
        🦞
      </motion.div>
      <h1 className="text-3xl font-bold text-white mb-2">欢迎使用 OpenClaw</h1>
      <p className="text-lg text-gray-400 mb-8">你的智能生活控制台</p>

      <div className="grid grid-cols-1 gap-3 w-full mb-8">
        {[
          { emoji: '🐟', title: 'AI客服', desc: '闲鱼自动回复，智能议价' },
          { emoji: '📈', title: '量化交易', desc: '自动化投资策略执行' },
          { emoji: '📱', title: '社媒运营', desc: '多平台内容自动发布' },
        ].map((feat) => (
          <div
            key={feat.title}
            className="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/10"
          >
            <span className="text-2xl">{feat.emoji}</span>
            <div className="text-left">
              <div className="text-sm font-medium text-white">{feat.title}</div>
              <div className="text-xs text-gray-400">{feat.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <Button onClick={onNext} className="w-full">
        开始设置
        <ChevronRight size={16} className="ml-1.5" />
      </Button>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Step 2: Feature Selection
──────────────────────────────────────────────────────────────── */

function StepFeatures({
  selected,
  onToggle,
}: {
  selected: Set<string>;
  onToggle: (id: string) => void;
}) {
  return (
    <div className="max-w-lg mx-auto">
      <h2 className="text-2xl font-bold text-white text-center mb-2">选择你需要的功能</h2>
      <p className="text-gray-400 text-center mb-6 text-sm">稍后可以在设置中修改</p>

      <div className="grid grid-cols-1 gap-3">
        {FEATURES.map((feat) => {
          const isSelected = selected.has(feat.id);
          return (
            <GlassCard
              key={feat.id}
              className={`p-4 cursor-pointer transition-all ${
                isSelected ? 'ring-2 ring-[var(--oc-brand)]' : ''
              } ${feat.alwaysOn ? 'opacity-80' : ''}`}
              onClick={() => !feat.alwaysOn && onToggle(feat.id)}
            >
              <div className="flex items-center gap-4">
                <span className="text-3xl">{feat.emoji}</span>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-semibold text-white">{feat.label}</h3>
                    {feat.alwaysOn && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--oc-brand)]/20 text-[var(--oc-brand)]">
                        默认开启
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-400 mt-0.5">{feat.description}</p>
                </div>
                <div
                  className={`w-6 h-6 rounded-full border-2 flex items-center justify-center transition-colors ${
                    isSelected
                      ? 'bg-[var(--oc-brand)] border-[var(--oc-brand)]'
                      : 'border-gray-500'
                  }`}
                >
                  {isSelected && <Check size={14} className="text-white" />}
                </div>
              </div>
            </GlassCard>
          );
        })}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Step 3: API Key Config
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

  return (
    <div className="max-w-lg mx-auto">
      <h2 className="text-2xl font-bold text-white text-center mb-2">配置核心服务</h2>
      <p className="text-gray-400 text-center mb-6 text-sm">连接 AI 服务以启用智能功能</p>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">API Key</label>
          <div className="relative">
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full px-3 py-2.5 pr-10 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[var(--oc-brand)] transition-all"
            />
            <button
              type="button"
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
              onClick={() => setShowKey(!showKey)}
            >
              {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">Base URL</label>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            className="w-full px-3 py-2.5 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-[var(--oc-brand)] transition-all"
          />
        </div>

        <p className="text-xs text-gray-500 text-center mt-4">
          💡 你可以稍后在设置中修改这些配置
        </p>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────
   Step 4: Completion
──────────────────────────────────────────────────────────────── */

function StepComplete({
  selectedFeatures,
  onFinish,
}: {
  selectedFeatures: Set<string>;
  onFinish: () => void;
}) {
  const selectedLabels = FEATURES.filter((f) => selectedFeatures.has(f.id));

  return (
    <div className="relative flex flex-col items-center text-center max-w-md mx-auto">
      <ConfettiEffect />

      <motion.div
        initial={{ scale: 0, rotate: -180 }}
        animate={{ scale: 1, rotate: 0 }}
        transition={{ type: 'spring', stiffness: 200, damping: 12 }}
        className="w-20 h-20 rounded-full bg-gradient-to-br from-green-400 to-emerald-600 flex items-center justify-center mb-6"
      >
        <Check size={40} className="text-white" />
      </motion.div>

      <h2 className="text-2xl font-bold text-white mb-2">一切就绪！</h2>
      <p className="text-gray-400 mb-6">以下功能已为你开启</p>

      <div className="flex flex-wrap gap-2 justify-center mb-8">
        {selectedLabels.map((feat) => (
          <motion.span
            key={feat.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + selectedLabels.indexOf(feat) * 0.1 }}
            className="px-3 py-1.5 rounded-full bg-[var(--oc-brand)]/20 text-[var(--oc-brand)] text-sm font-medium"
          >
            {feat.emoji} {feat.label}
          </motion.span>
        ))}
      </div>

      <Button onClick={onFinish} className="w-full">
        进入控制台
        <ChevronRight size={16} className="ml-1.5" />
      </Button>
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
      } catch { /* 静默失败，用户可稍后在设置中配置 */ }
    }
    if (baseUrl.trim()) {
      try {
        await api.saveEnvValue('LLM_BASE_URL', baseUrl.trim());
      } catch { /* 静默失败 */ }
    }

    onComplete();
  }, [selectedFeatures, apiKey, baseUrl, onComplete]);

  return (
    <div className="fixed inset-0 z-50 bg-dark-900 flex flex-col">
      {/* Background decoration */}
      <div className="fixed inset-0 bg-gradient-radial pointer-events-none" />

      {/* macOS draggable title bar area */}
      <div className="h-12 flex-shrink-0" data-tauri-drag-region="" />

      {/* Progress bar + 跳过按钮 */}
      <div className="relative z-10 px-8 mb-6">
        <div className="max-w-lg mx-auto flex items-center gap-2">
          {Array.from({ length: TOTAL_STEPS }, (_, i) => (
            <div key={i} className="flex-1 h-1 rounded-full overflow-hidden bg-white/10">
              <motion.div
                className="h-full bg-[var(--oc-brand)] rounded-full"
                initial={false}
                animate={{ width: i <= step ? '100%' : '0%' }}
                transition={{ duration: 0.3 }}
              />
            </div>
          ))}
          {/* 跳过引导按钮：所有步骤（除完成页）都可以跳过 */}
          {step < TOTAL_STEPS - 1 && (
            <button
              onClick={handleFinish}
              className="ml-2 text-xs text-gray-500 hover:text-gray-300 transition-colors whitespace-nowrap"
              aria-label="跳过引导"
            >
              跳过
            </button>
          )}
        </div>
      </div>

      {/* Step content */}
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

      {/* Navigation footer */}
      <div className="relative z-10 px-8 pb-8">
        <div className="max-w-lg mx-auto flex items-center justify-between">
          {step > 0 && step < TOTAL_STEPS - 1 ? (
            <Button variant="outline" onClick={goBack}>
              <ChevronLeft size={16} className="mr-1" />
              上一步
            </Button>
          ) : (
            <div />
          )}
          {step > 0 && step < TOTAL_STEPS - 1 && (
            <Button onClick={goNext}>
              下一步
              <ChevronRight size={16} className="ml-1" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
