import { motion } from 'framer-motion';
import {
  User,
  Shield,
  Cpu,
  HardDrive,
  Wifi,
  Key,
  Bell,
  Settings2,
  Download,
  RotateCcw,
  Trash2,
  FileText,
  Stethoscope,
  Check,
  MemoryStick,
} from 'lucide-react';

/* ====== 入场动画 ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.07 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 模拟数据 ====== */

/** API 密钥配置 */
interface ApiKeyItem {
  id: string;
  name: string;
  configured: boolean;
  maskedKey: string;
}

const mockApiKeys: ApiKeyItem[] = [
  { id: 'openai', name: 'OpenAI', configured: true, maskedKey: 'sk-...Xk4m' },
  { id: 'anthropic', name: 'Anthropic', configured: true, maskedKey: 'sk-ant-...9f2B' },
  { id: 'deepseek', name: 'DeepSeek', configured: true, maskedKey: 'sk-...L7pQ' },
  { id: 'ibkr', name: 'IBKR', configured: true, maskedKey: 'DU...8842' },
];

/** 通知开关 */
interface NotifyToggle {
  id: string;
  label: string;
  enabled: boolean;
}

const mockNotifications: NotifyToggle[] = [
  { id: 'telegram', label: 'Telegram 通知', enabled: true },
  { id: 'email', label: '邮件通知', enabled: false },
  { id: 'trade', label: '交易提醒', enabled: true },
  { id: 'error', label: '错误告警', enabled: true },
];

/** 高级设置项 */
interface AdvancedItem {
  id: string;
  label: string;
  value: string;
  type: 'toggle' | 'text';
}

const mockAdvanced: AdvancedItem[] = [
  { id: 'dev', label: '开发者模式', value: 'true', type: 'toggle' },
  { id: 'log', label: '日志级别', value: 'DEBUG', type: 'text' },
  { id: 'update', label: '自动更新', value: 'true', type: 'toggle' },
  { id: 'backup', label: '数据备份', value: '每日', type: 'text' },
];

/** 操作按钮 */
interface ActionButton {
  id: string;
  label: string;
  icon: React.ElementType;
  accent: string;
}

const mockActions: ActionButton[] = [
  { id: 'export', label: '导出配置', icon: Download, accent: 'var(--accent-cyan)' },
  { id: 'reset', label: '重置设置', icon: RotateCcw, accent: 'var(--accent-amber)' },
  { id: 'cache', label: '清除缓存', icon: Trash2, accent: 'var(--accent-red)' },
  { id: 'logs', label: '查看日志', icon: FileText, accent: 'var(--accent-purple)' },
  { id: 'diag', label: '系统诊断', icon: Stethoscope, accent: 'var(--accent-green)' },
];

/* ====== 主组件 ====== */

/**
 * 设置页面 — Sonic Abyss 终端美学
 * 12 列 Bento Grid 布局，展示系统配置的全部关键信息
 */
/** 接收外部 props（兼容 App.tsx 传入的 onEnvironmentChange） */
interface SettingsProps {
  onEnvironmentChange?: () => void;
}

export function Settings(_props: SettingsProps) {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== Row 1: 账户信息 (span-8) + 系统状态 (span-4) ====== */}

        {/* 账户信息 */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            {/* 标题区域 */}
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(0,212,255,0.15)' }}
              >
                <User size={20} style={{ color: 'var(--accent-cyan)' }} />
              </div>
              <div>
                <h2 className="font-display text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  账户信息 // ACCOUNT
                </h2>
                <p className="font-mono text-[10px] tracking-widest" style={{ color: 'var(--text-tertiary)' }}>
                  IDENTITY // SYSTEM // PROFILE
                </p>
              </div>
            </div>

            {/* 个人信息网格 */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <InfoBlock label="用户名" value="管理员" accent="var(--accent-cyan)" />
              <InfoBlock label="Telegram ID" value="@openclaw_bot" accent="var(--accent-purple)" />
              <InfoBlock label="系统版本" value="v2.0.0" accent="var(--accent-green)" />
              <InfoBlock label="运行时间" value="47 天" accent="var(--accent-amber)" />
              <InfoBlock label="最后登录" value="2026-04-19 09:32" accent="var(--text-secondary)" />
              <InfoBlock label="许可证" value="Pro" accent="var(--accent-cyan)" />
            </div>
          </div>
        </motion.div>

        {/* 系统状态 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-5">
              <Cpu size={16} style={{ color: 'var(--accent-green)' }} />
              <span className="text-label" style={{ color: 'var(--accent-green)' }}>
                SYSTEM STATUS
              </span>
            </div>

            <div className="space-y-4">
              <ResourceBar icon={Cpu} label="CPU 使用率" value={12} max={100} unit="%" accent="var(--accent-cyan)" />
              <ResourceBar icon={MemoryStick} label="内存" value={2.1} max={8} unit="GB" accent="var(--accent-purple)" />
              <ResourceBar icon={HardDrive} label="磁盘" value={45.2} max={256} unit="GB" accent="var(--accent-amber)" />

              {/* 网络状态 */}
              <div className="flex items-center gap-3 p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
                <Wifi size={14} style={{ color: 'var(--accent-green)' }} />
                <span className="font-mono text-[11px] flex-1" style={{ color: 'var(--text-secondary)' }}>
                  网络状态
                </span>
                <div className="flex items-center gap-1.5">
                  <div className="relative">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--accent-green)' }} />
                    <div
                      className="absolute inset-0 w-2.5 h-2.5 rounded-full animate-ping opacity-30"
                      style={{ background: 'var(--accent-green)' }}
                    />
                  </div>
                  <span className="font-mono text-xs font-bold" style={{ color: 'var(--accent-green)' }}>
                    在线
                  </span>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== Row 2: API 密钥 (span-4) + 通知设置 (span-4) + 高级设置 (span-4) ====== */}

        {/* API 密钥管理 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Key size={16} style={{ color: 'var(--accent-amber)' }} />
              <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
                API KEYS
              </span>
            </div>

            <div className="space-y-3">
              {mockApiKeys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center gap-3 p-3 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}
                >
                  {/* 状态图标 */}
                  <div
                    className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: key.configured ? 'rgba(0,255,170,0.12)' : 'rgba(255,0,60,0.12)' }}
                  >
                    {key.configured ? (
                      <Check size={12} style={{ color: 'var(--accent-green)' }} />
                    ) : (
                      <Shield size={12} style={{ color: 'var(--accent-red)' }} />
                    )}
                  </div>

                  {/* 名称 */}
                  <span className="font-mono text-xs font-medium flex-1" style={{ color: 'var(--text-primary)' }}>
                    {key.name}
                  </span>

                  {/* 密钥预览 */}
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                    {key.maskedKey}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* 通知设置 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Bell size={16} style={{ color: 'var(--accent-purple)' }} />
              <span className="text-label" style={{ color: 'var(--accent-purple)' }}>
                NOTIFICATIONS
              </span>
            </div>

            <div className="space-y-3">
              {mockNotifications.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}
                >
                  <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {item.label}
                  </span>

                  {/* 纯 CSS 开关 — 不依赖 shadcn */}
                  <div
                    className="w-9 h-5 rounded-full relative transition-colors cursor-pointer"
                    style={{
                      background: item.enabled ? 'var(--accent-cyan)' : 'var(--dark-500)',
                    }}
                  >
                    <div
                      className="absolute top-0.5 w-4 h-4 rounded-full transition-all"
                      style={{
                        background: 'var(--text-primary)',
                        left: item.enabled ? '18px' : '2px',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* 高级设置 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full">
            <div className="flex items-center gap-2 mb-4">
              <Settings2 size={16} style={{ color: 'var(--accent-cyan)' }} />
              <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                ADVANCED
              </span>
            </div>

            <div className="space-y-3">
              {mockAdvanced.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3 rounded-xl"
                  style={{ background: 'var(--bg-base)' }}
                >
                  <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {item.label}
                  </span>

                  {item.type === 'toggle' ? (
                    <div
                      className="w-9 h-5 rounded-full relative transition-colors cursor-pointer"
                      style={{
                        background: item.value === 'true' ? 'var(--accent-cyan)' : 'var(--dark-500)',
                      }}
                    >
                      <div
                        className="absolute top-0.5 w-4 h-4 rounded-full transition-all"
                        style={{
                          background: 'var(--text-primary)',
                          left: item.value === 'true' ? '18px' : '2px',
                        }}
                      />
                    </div>
                  ) : (
                    <span className="font-mono text-xs font-bold" style={{ color: 'var(--accent-cyan)' }}>
                      {item.value}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* ====== Row 3: 操作区 (span-12) ====== */}

        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            <div className="flex items-center gap-2 mb-5">
              <Shield size={16} style={{ color: 'var(--text-tertiary)' }} />
              <span className="text-label" style={{ color: 'var(--text-tertiary)' }}>
                ACTIONS
              </span>
            </div>

            <div className="flex flex-wrap gap-3">
              {mockActions.map((action) => (
                <button
                  key={action.id}
                  className="flex items-center gap-2.5 px-5 py-3 rounded-xl transition-all cursor-pointer"
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--glass-border)',
                    color: action.accent,
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = action.accent;
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.borderColor = 'var(--glass-border)';
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-card)';
                  }}
                >
                  <action.icon size={16} />
                  <span className="font-mono text-xs font-medium">{action.label}</span>
                </button>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}

/* ====== 子组件 ====== */

/** 账户信息块 */
function InfoBlock({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
      <span className="text-label block mb-1.5" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </span>
      <span className="font-mono text-sm font-medium" style={{ color: accent }}>
        {value}
      </span>
    </div>
  );
}

/** 资源使用率条 */
function ResourceBar({
  icon: Icon,
  label,
  value,
  max,
  unit,
  accent,
}: {
  icon: React.ElementType;
  label: string;
  value: number;
  max: number;
  unit: string;
  accent: string;
}) {
  const pct = Math.round((value / max) * 100);

  return (
    <div className="p-3 rounded-xl" style={{ background: 'var(--bg-base)' }}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Icon size={12} style={{ color: accent }} />
          <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
            {label}
          </span>
        </div>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
          {value}{unit} / {max}{unit}
        </span>
      </div>
      <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: accent }}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}
