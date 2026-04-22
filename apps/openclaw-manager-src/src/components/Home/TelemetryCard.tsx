import { useLanguage } from '@/i18n';

/* 遥测数据类型 */
interface TelemetryData {
  llmCostDaily: number;
  activeBots: number;
  poolActive: number;
  poolTotal: number;
  memoryEntries: number;
}

interface Props {
  data: TelemetryData;
  isRunning: boolean;
}

/* 遥测指标配置 — labelKey 用于 i18n 查找 */
interface MetricConfig {
  labelKey: string;
  getValue: (d: TelemetryData) => string;
  accent: string;
}

const metrics: MetricConfig[] = [
  {
    labelKey: 'telemetry.llmDailyCost',
    getValue: (d) => `$${d.llmCostDaily.toFixed(2)}`,
    accent: 'var(--accent-cyan)',
  },
  {
    labelKey: 'telemetry.activeBots',
    getValue: (d) => String(d.activeBots),
    accent: 'var(--accent-green)',
  },
  {
    labelKey: 'telemetry.modelPool',
    getValue: (d) => `${d.poolActive}/${d.poolTotal}`,
    accent: 'var(--accent-purple)',
  },
  {
    labelKey: 'telemetry.memoryEntries',
    getValue: (d) => d.memoryEntries > 0 ? d.memoryEntries.toLocaleString() : '0',
    accent: 'var(--accent-amber)',
  },
];

/**
 * 遥测卡片 — 2x2 指标网格
 * 展示 LLM 费用、Bot 数量、API 池、记忆条目
 */
export function TelemetryCard({ data, isRunning }: Props) {
  const { t } = useLanguage();

  return (
    <div className="abyss-card p-6 h-full flex flex-col">
      <span className="text-label">{t('telemetry.title')}</span>

      <div className="grid grid-cols-2 gap-4 mt-4 flex-1">
        {metrics.map((m) => (
          <div key={m.labelKey} className="flex flex-col justify-center">
            <span className="text-label text-[10px]" style={{ color: m.accent }}>
              {t(m.labelKey)}
            </span>
            <span className="text-metric mt-1">{m.getValue(data)}</span>
          </div>
        ))}
      </div>

      {/* 底部运行状态 */}
      <div className="mt-4 pt-3" style={{ borderTop: '1px solid var(--glass-border)' }}>
        <div className="flex items-center gap-2">
          <span className={isRunning ? 'status-dot-green' : 'status-dot-red'} />
          <span className="font-mono text-[10px] uppercase" style={{ color: isRunning ? 'var(--accent-green)' : 'var(--accent-red)' }}>
            {isRunning ? t('telemetry.systemOk') : t('telemetry.noData')}
          </span>
        </div>
      </div>
    </div>
  );
}
