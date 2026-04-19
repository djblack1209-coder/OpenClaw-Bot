import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Shield,
  AlertTriangle,
  Wifi,
  WifiOff,
  Zap,
  Flame,
  CloudLightning,
  Swords,
  Globe,
  Radio,
  ArrowUp,
  ArrowDown,
  Minus,
  Terminal,
} from 'lucide-react';

/* ====== 入场动画配置（与 Home 一致） ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== 类型定义 ====== */

/** 国家风险条目 */
interface CountryRisk {
  country: string;
  code: string;
  score: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  change24h: number; // 24小时变化（正数=上升，负数=下降）
}

/** 冲突区域 */
interface ConflictZone {
  region: string;
  severity: 'HIGH' | 'CRITICAL';
  description: string;
}

/** 情报日志条目 */
interface IntelEntry {
  id: string;
  timestamp: string;
  category: 'CONFLICT' | 'CYBER' | 'CLIMATE' | 'ECONOMIC';
  message: string;
}

/* ====== 模拟数据 ====== */

/** 全球综合风险分数 */
const GLOBAL_RISK_SCORE = 62;
const GLOBAL_RISK_SEVERITY: 'LOW' | 'MEDIUM' | 'HIGH' = 'MEDIUM';

/** 前 5 高风险国家 */
const TOP_RISK_COUNTRIES: CountryRisk[] = [
  { country: 'Ukraine',      code: 'UA', score: 94, severity: 'CRITICAL', change24h: 2.1 },
  { country: 'Israel',       code: 'IL', score: 88, severity: 'CRITICAL', change24h: -1.3 },
  { country: 'Myanmar',      code: 'MM', score: 79, severity: 'HIGH',     change24h: 0.5 },
  { country: 'Sudan',        code: 'SD', score: 76, severity: 'HIGH',     change24h: 3.8 },
  { country: 'Yemen',        code: 'YE', score: 71, severity: 'HIGH',     change24h: -0.2 },
];

/** 活跃冲突区域 */
const CONFLICT_ZONES: ConflictZone[] = [
  { region: 'Eastern Europe',   severity: 'CRITICAL', description: 'Russia-Ukraine 持续高强度冲突' },
  { region: 'Middle East',      severity: 'CRITICAL', description: 'Gaza 地区人道主义危机' },
  { region: 'East Africa',      severity: 'HIGH',     description: 'Sudan 内战扩大化' },
];

/** 情报日志流 */
const INTEL_FEED: IntelEntry[] = [
  { id: '1', timestamp: '14:32:08', category: 'CONFLICT',  message: '[UA] 扎波罗热方向检测到新一轮炮击活动，预计影响平民疏散路线' },
  { id: '2', timestamp: '14:28:41', category: 'CYBER',     message: '[Global] Cloudflare 报告亚太地区 DDoS 攻击流量激增 340%' },
  { id: '3', timestamp: '14:25:15', category: 'ECONOMIC',  message: '[CN] 人民币离岸汇率突破 7.28 关口，央行释放稳定信号' },
  { id: '4', timestamp: '14:21:33', category: 'CLIMATE',   message: '[JP] 气象厅发布九州地区暴雨特别警报，24小时降水量超 300mm' },
  { id: '5', timestamp: '14:18:02', category: 'CONFLICT',  message: '[SD] 快速支援部队控制北达尔富尔首府，联合国呼吁紧急人道主义通道' },
  { id: '6', timestamp: '14:14:47', category: 'CYBER',     message: '[US] CISA 发布关键基础设施漏洞通告 CVE-2026-3891，CVSS 9.8' },
  { id: '7', timestamp: '14:10:22', category: 'ECONOMIC',  message: '[EU] 欧洲央行维持利率不变，但暗示 Q3 可能降息 25bp' },
  { id: '8', timestamp: '14:06:59', category: 'CLIMATE',   message: '[CA] 不列颠哥伦比亚省 3 处山火失控，过火面积超 12,000 公顷' },
  { id: '9', timestamp: '14:03:11', category: 'CONFLICT',  message: '[MM] 缅甸民族抵抗力量在掸邦北部推进，控制 2 个关键据点' },
  { id: '10', timestamp: '13:58:44', category: 'CYBER',    message: '[RU] 多家俄罗斯银行遭受供应链攻击，支付系统中断约 2 小时' },
];

/* ====== 工具函数 ====== */

/** 根据严重度返回对应颜色变量 */
function severityColor(severity: string): string {
  switch (severity) {
    case 'CRITICAL': return 'var(--accent-red)';
    case 'HIGH':     return 'var(--accent-amber)';
    case 'MEDIUM':   return 'var(--accent-amber)';
    case 'LOW':      return 'var(--accent-green)';
    default:         return 'var(--text-tertiary)';
  }
}

/** 根据情报类别返回对应颜色和图标 */
function categoryMeta(category: IntelEntry['category']): { color: string; bg: string } {
  switch (category) {
    case 'CONFLICT': return { color: 'var(--accent-red)',    bg: 'rgba(255, 0, 60, 0.12)' };
    case 'CYBER':    return { color: 'var(--accent-cyan)',   bg: 'rgba(0, 212, 255, 0.12)' };
    case 'CLIMATE':  return { color: 'var(--accent-amber)',  bg: 'rgba(251, 191, 36, 0.12)' };
    case 'ECONOMIC': return { color: 'var(--accent-purple)', bg: 'rgba(167, 139, 250, 0.12)' };
  }
}

/** 渲染24小时变化指示器 */
function ChangeIndicator({ value }: { value: number }) {
  if (value > 0) {
    return (
      <span className="flex items-center gap-0.5 font-mono text-[10px]" style={{ color: 'var(--accent-red)' }}>
        <ArrowUp size={10} />+{value.toFixed(1)}
      </span>
    );
  }
  if (value < 0) {
    return (
      <span className="flex items-center gap-0.5 font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
        <ArrowDown size={10} />{value.toFixed(1)}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-0.5 font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
      <Minus size={10} />0.0
    </span>
  );
}

/* ====== 主组件 ====== */

/**
 * 全球监控面板 — Sonic Abyss Bento Grid 布局
 * 12 列 CSS Grid，玻璃卡片 + 终端美学
 * 展示地缘风险、冲突、基础设施状态、气候灾害与情报流
 */
export function WorldMonitor() {
  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 第一行：全球风险分数 (span-4) + 全球威胁地图 (span-8) ====== */}

        {/* 全球综合风险分数卡 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              GLOBAL RISK INDEX
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              综合风险指数
            </h3>

            {/* 大数字展示区 */}
            <div className="flex-1 flex flex-col items-center justify-center py-6">
              <div className="relative">
                {/* 外圈脉冲光晕 */}
                <motion.div
                  className="absolute inset-0 rounded-full"
                  style={{
                    background: `radial-gradient(circle, ${severityColor(GLOBAL_RISK_SEVERITY)}20 0%, transparent 70%)`,
                  }}
                  animate={{ scale: [1, 1.3, 1], opacity: [0.6, 0.2, 0.6] }}
                  transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                />
                <span
                  className="text-metric relative z-10"
                  style={{
                    fontSize: '72px',
                    lineHeight: 1,
                    color: severityColor(GLOBAL_RISK_SEVERITY),
                  }}
                >
                  {GLOBAL_RISK_SCORE}
                </span>
              </div>
              <span className="font-mono text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
                / 100
              </span>
            </div>

            {/* 严重度标签 + 状态指示 */}
            <div className="flex items-center justify-between">
              <span
                className="px-3 py-1 rounded-full font-mono text-[10px] uppercase tracking-wider"
                style={{
                  background: `${severityColor(GLOBAL_RISK_SEVERITY)}15`,
                  color: severityColor(GLOBAL_RISK_SEVERITY),
                  border: `1px solid ${severityColor(GLOBAL_RISK_SEVERITY)}30`,
                }}
              >
                {GLOBAL_RISK_SEVERITY}
              </span>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="status-dot-green"
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                  LIVE
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* 全球威胁地图卡 */}
        <motion.div className="col-span-12 lg:col-span-8" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-label" style={{ color: 'var(--accent-red)' }}>
                  GLOBAL THREAT MAP
                </span>
                <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                  全球威胁地图
                </h3>
              </div>
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                RISK OVERLAY // 30 COUNTRIES
              </span>
            </div>

            {/* 高风险国家表格 */}
            <div className="mt-4 flex-1">
              {/* 表头 */}
              <div
                className="grid grid-cols-[1fr_80px_100px_80px] gap-2 px-3 py-2 rounded-lg mb-1"
                style={{ background: 'rgba(255,255,255,0.02)' }}
              >
                <span className="text-label" style={{ fontSize: '10px' }}>COUNTRY</span>
                <span className="text-label text-right" style={{ fontSize: '10px' }}>SCORE</span>
                <span className="text-label text-center" style={{ fontSize: '10px' }}>SEVERITY</span>
                <span className="text-label text-right" style={{ fontSize: '10px' }}>24H</span>
              </div>

              {/* 数据行 */}
              {TOP_RISK_COUNTRIES.map((c, i) => (
                <motion.div
                  key={c.code}
                  className="grid grid-cols-[1fr_80px_100px_80px] gap-2 px-3 py-2.5 rounded-lg transition-colors"
                  style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)' }}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.08, duration: 0.3 }}
                >
                  {/* 国家名称 */}
                  <div className="flex items-center gap-2">
                    <Globe size={13} style={{ color: severityColor(c.severity), flexShrink: 0 }} />
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      {c.country}
                    </span>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {c.code}
                    </span>
                  </div>

                  {/* 分数 */}
                  <span
                    className="font-mono text-xs text-right font-bold"
                    style={{ color: severityColor(c.severity) }}
                  >
                    {c.score}
                  </span>

                  {/* 严重度徽章 */}
                  <div className="flex justify-center">
                    <span
                      className="px-2 py-0.5 rounded-full font-mono text-[9px] uppercase tracking-wider"
                      style={{
                        background: `${severityColor(c.severity)}12`,
                        color: severityColor(c.severity),
                        border: `1px solid ${severityColor(c.severity)}25`,
                      }}
                    >
                      {c.severity}
                    </span>
                  </div>

                  {/* 24小时变化 */}
                  <div className="flex justify-end items-center">
                    <ChangeIndicator value={c.change24h} />
                  </div>
                </motion.div>
              ))}
            </div>

            {/* 底部备注 */}
            <div className="flex items-center gap-2 mt-3 pt-3" style={{ borderTop: '1px solid var(--glass-border)' }}>
              <Radio size={12} style={{ color: 'var(--text-disabled)' }} />
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                数据每 15 分钟更新 · 来源: ACLED / GDELT / SIPRI
              </span>
            </div>
          </div>
        </motion.div>

        {/* ====== 第二行：活跃冲突 (span-4) + 基础设施 (span-4) + 气候灾害 (span-4) ====== */}

        {/* 活跃冲突卡 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-red)' }}>
              ACTIVE CONFLICTS
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              活跃冲突区
            </h3>

            {/* 冲突数量大数字 */}
            <div className="flex items-baseline gap-2 mt-4">
              <span className="text-metric" style={{ color: 'var(--accent-red)' }}>
                {CONFLICT_ZONES.length}
              </span>
              <span className="text-label">活跃区域</span>
            </div>

            {/* 冲突列表 */}
            <div className="flex flex-col gap-2.5 mt-4 flex-1">
              {CONFLICT_ZONES.map((zone) => (
                <div
                  key={zone.region}
                  className="flex items-start gap-3 p-3 rounded-xl"
                  style={{ background: 'rgba(255,255,255,0.02)' }}
                >
                  <Swords
                    size={14}
                    className="mt-0.5 flex-shrink-0"
                    style={{ color: severityColor(zone.severity) }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
                        {zone.region}
                      </span>
                      <span
                        className="px-1.5 py-0.5 rounded font-mono text-[8px] uppercase"
                        style={{
                          background: `${severityColor(zone.severity)}12`,
                          color: severityColor(zone.severity),
                        }}
                      >
                        {zone.severity}
                      </span>
                    </div>
                    <p className="font-mono text-[10px] mt-1 leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>
                      {zone.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </motion.div>

        {/* 基础设施状态卡 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              INFRASTRUCTURE
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              基础设施状态
            </h3>

            <div className="flex flex-col gap-4 mt-5 flex-1">
              {/* 互联网中断 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(255, 0, 60, 0.1)' }}
                  >
                    <WifiOff size={15} style={{ color: 'var(--accent-red)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      互联网中断
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      Internet Outages
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-red)' }}>
                  7
                </span>
              </div>

              {/* GPS 干扰 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(251, 191, 36, 0.1)' }}
                  >
                    <AlertTriangle size={15} style={{ color: 'var(--accent-amber)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      GPS 干扰
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      GPS Interference
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-amber)' }}>
                  12
                </span>
              </div>

              {/* 电力网络 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(0, 255, 170, 0.1)' }}
                  >
                    <Zap size={15} style={{ color: 'var(--accent-green)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      电力网络
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      Power Grid Status
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="status-dot-green" />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                    STABLE
                  </span>
                </div>
              </div>

              {/* 海底光缆 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(0, 212, 255, 0.1)' }}
                  >
                    <Wifi size={15} style={{ color: 'var(--accent-cyan)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      海底光缆
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      Subsea Cables
                    </p>
                  </div>
                </div>
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-amber)' }}>
                  2 DEGRADED
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* 气候与灾害卡 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              CLIMATE & DISASTERS
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              气候与灾害
            </h3>

            <div className="flex flex-col gap-4 mt-5 flex-1">
              {/* 地震活动 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(251, 191, 36, 0.1)' }}
                  >
                    <Shield size={15} style={{ color: 'var(--accent-amber)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      地震活动
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      M5.0+ / 24h
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-amber)' }}>
                  3
                </span>
              </div>

              {/* 山火告警 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(255, 0, 60, 0.1)' }}
                  >
                    <Flame size={15} style={{ color: 'var(--accent-red)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      山火告警
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      Wildfire Alerts
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-red)' }}>
                  5
                </span>
              </div>

              {/* 气候异常 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(167, 139, 250, 0.1)' }}
                  >
                    <CloudLightning size={15} style={{ color: 'var(--accent-purple)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      气候异常
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      Anomalies Detected
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-purple)' }}>
                  8
                </span>
              </div>

              {/* 极端天气预警 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(0, 212, 255, 0.1)' }}
                  >
                    <AlertTriangle size={15} style={{ color: 'var(--accent-cyan)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      极端天气
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      Severe Weather
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-cyan)' }}>
                  14
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 第三行：情报终端流 (span-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            {/* 标题栏 — 终端风格 */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Terminal size={14} style={{ color: 'var(--accent-cyan)' }} />
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  INTELLIGENCE FEED
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="status-dot-green"
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                  STREAMING
                </span>
              </div>
            </div>

            {/* 终端日志列表 */}
            <div
              className="rounded-xl p-3 max-h-[280px] overflow-y-auto scroll-container"
              style={{ background: 'rgba(0,0,0,0.3)' }}
            >
              {INTEL_FEED.map((entry, i) => {
                const meta = categoryMeta(entry.category);
                return (
                  <motion.div
                    key={entry.id}
                    className={clsx(
                      'flex items-start gap-3 px-3 py-2 rounded-lg',
                      i % 2 === 0 ? 'bg-transparent' : 'bg-white/[0.015]'
                    )}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5 + i * 0.05, duration: 0.25 }}
                  >
                    {/* 时间戳 */}
                    <span
                      className="font-mono text-[10px] flex-shrink-0 mt-0.5"
                      style={{ color: 'var(--text-disabled)', minWidth: '56px' }}
                    >
                      {entry.timestamp}
                    </span>

                    {/* 类别徽章 */}
                    <span
                      className="px-1.5 py-0.5 rounded font-mono text-[9px] uppercase tracking-wider flex-shrink-0 mt-0.5"
                      style={{
                        background: meta.bg,
                        color: meta.color,
                        minWidth: '60px',
                        textAlign: 'center',
                      }}
                    >
                      {entry.category}
                    </span>

                    {/* 消息内容 */}
                    <span
                      className="font-mono text-[11px] leading-relaxed"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {entry.message}
                    </span>
                  </motion.div>
                );
              })}
            </div>

            {/* 底部信息 */}
            <div className="flex items-center justify-between mt-3">
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                显示最近 {INTEL_FEED.length} 条 · 来源: OSINT / GDELT / ACLED / CVE
              </span>
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                AUTO-REFRESH 60s
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
