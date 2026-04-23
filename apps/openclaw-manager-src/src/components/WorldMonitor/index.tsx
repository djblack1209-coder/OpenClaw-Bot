import { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  ComposableMap,
  Geographies,
  Geography,
  ZoomableGroup,
} from 'react-simple-maps';
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
  ExternalLink,
  Map,
  Loader2,
  Clock,
} from 'lucide-react';
import { clawbotFetchJson } from '../../lib/tauri-core';
import { api } from '../../lib/api';
import { useLanguage } from '../../i18n';
import { LoadingState } from '../shared/LoadingState';
import { SimpleErrorState as ErrorState } from '../shared/ErrorState';

/* ====== TopoJSON 地图源 — 本地打包，避免 Tauri CSP 拦截 ====== */
const GEO_URL = '/countries-110m.json';

/* ====== 自动刷新间隔（毫秒） ====== */
const REFRESH_INTERVAL = 30_000;

/* ====== 入场动画配置（与 Home 一致） ====== */
const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
};

/* ====== API 返回类型定义 ====== */

/** 国家风险条目（API 返回格式） */
interface RiskApiItem {
  country_code: string;
  country_name: string;
  composite_score: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  sub_scores: Record<string, number>;
  change_24h: number;
}

/** 全局风险 API 返回 */
interface GlobalRiskApi {
  score: number;
  severity: string;
  [key: string]: unknown;
}

/** 新闻条目 API 返回 */
interface NewsApiItem {
  title: string;
  source: string;
  category: string;
  published_at: string;
  summary: string;
  threat_level: string;
}

/* ====== 内部显示类型 ====== */

/** 国家风险条目（显示用） */
interface CountryRisk {
  country: string;
  code: string;
  score: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  change24h: number;
  link: string;
}

/** 情报日志条目 */
interface IntelEntry {
  id: string;
  timestamp: string;
  category: 'CONFLICT' | 'CYBER' | 'CLIMATE' | 'ECONOMIC';
  message: string;
}

/** 地图悬停提示信息 */
interface TooltipInfo {
  name: string;
  score: number;
  level: string;
  x: number;
  y: number;
}

/* ====== 严重度 key 映射 ====== */
const SEVERITY_I18N_KEY: Record<string, string> = {
  CRITICAL: 'worldMonitor.severityCritical',
  HIGH: 'worldMonitor.severityHigh',
  MEDIUM: 'worldMonitor.severityMedium',
  LOW: 'worldMonitor.severityLow',
};

/** 情报类别 key 映射 */
const CATEGORY_I18N_KEY: Record<string, string> = {
  CONFLICT: 'worldMonitor.catConflict',
  CYBER: 'worldMonitor.catCyber',
  CLIMATE: 'worldMonitor.catClimate',
  ECONOMIC: 'worldMonitor.catEconomic',
};

/** ISO alpha-2 → alpha-3 映射（用于地图着色） */
const ISO2_TO_ISO3: Record<string, string> = {
  AF: 'AFG', AL: 'ALB', DZ: 'DZA', AO: 'AGO', AR: 'ARG', AU: 'AUS', AT: 'AUT',
  BD: 'BGD', BE: 'BEL', BO: 'BOL', BR: 'BRA', BG: 'BGR', BF: 'BFA', BI: 'BDI',
  KH: 'KHM', CM: 'CMR', CA: 'CAN', CF: 'CAF', TD: 'TCD', CL: 'CHL', CN: 'CHN',
  CO: 'COL', CG: 'COG', CD: 'COD', CR: 'CRI', HR: 'HRV', CU: 'CUB', CY: 'CYP',
  CZ: 'CZE', DK: 'DNK', DO: 'DOM', EC: 'ECU', EG: 'EGY', SV: 'SLV', GQ: 'GNQ',
  ER: 'ERI', EE: 'EST', ET: 'ETH', FI: 'FIN', FR: 'FRA', GA: 'GAB', GM: 'GMB',
  GE: 'GEO', DE: 'DEU', GH: 'GHA', GR: 'GRC', GT: 'GTM', GN: 'GIN', GY: 'GUY',
  HT: 'HTI', HN: 'HND', HU: 'HUN', IN: 'IND', ID: 'IDN', IR: 'IRN', IQ: 'IRQ',
  IE: 'IRL', IL: 'ISR', IT: 'ITA', CI: 'CIV', JM: 'JAM', JP: 'JPN', JO: 'JOR',
  KZ: 'KAZ', KE: 'KEN', KP: 'PRK', KR: 'KOR', KW: 'KWT', KG: 'KGZ', LA: 'LAO',
  LV: 'LVA', LB: 'LBN', LS: 'LSO', LR: 'LBR', LY: 'LBY', LT: 'LTU', LU: 'LUX',
  MG: 'MDG', MW: 'MWI', MY: 'MYS', ML: 'MLI', MR: 'MRT', MX: 'MEX', MN: 'MNG',
  MA: 'MAR', MZ: 'MOZ', MM: 'MMR', NA: 'NAM', NP: 'NPL', NL: 'NLD', NZ: 'NZL',
  NI: 'NIC', NE: 'NER', NG: 'NGA', NO: 'NOR', OM: 'OMN', PK: 'PAK', PA: 'PAN',
  PG: 'PNG', PY: 'PRY', PE: 'PER', PH: 'PHL', PL: 'POL', PT: 'PRT', QA: 'QAT',
  RO: 'ROU', RU: 'RUS', RW: 'RWA', SA: 'SAU', SN: 'SEN', SL: 'SLE', SG: 'SGP',
  SK: 'SVK', SI: 'SVN', SO: 'SOM', ZA: 'ZAF', ES: 'ESP', LK: 'LKA', SD: 'SDN',
  SR: 'SUR', SZ: 'SWZ', SE: 'SWE', CH: 'CHE', SY: 'SYR', TW: 'TWN', TJ: 'TJK',
  TZ: 'TZA', TH: 'THA', TG: 'TGO', TT: 'TTO', TN: 'TUN', TR: 'TUR', TM: 'TKM',
  UG: 'UGA', UA: 'UKR', AE: 'ARE', GB: 'GBR', US: 'USA', UY: 'URY', UZ: 'UZB',
  VE: 'VEN', VN: 'VNM', YE: 'YEM', ZM: 'ZMB', ZW: 'ZWE',
};

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

/** 根据风险分数返回填充颜色（地图热力色阶） */
function riskScoreToFill(score: number): string {
  if (score >= 85) return '#ff003c';
  if (score >= 70) return '#ff6b35';
  if (score >= 50) return '#fbbf24';
  if (score >= 30) return '#00d4ff';
  return 'rgba(255,255,255,0.08)';
}

/** 根据风险分数返回等级 i18n key */
function riskScoreToLevel(score: number): string {
  if (score >= 85) return 'worldMonitor.levelCritical';
  if (score >= 70) return 'worldMonitor.levelHigh';
  if (score >= 50) return 'worldMonitor.levelElevated';
  if (score >= 30) return 'worldMonitor.levelModerate';
  return 'worldMonitor.levelLow';
}

/** 根据情报类别返回对应颜色和背景色 */
function categoryMeta(category: string): { color: string; bg: string } {
  switch (category) {
    case 'CONFLICT': return { color: 'var(--accent-red)',    bg: 'rgba(255, 0, 60, 0.12)' };
    case 'CYBER':    return { color: 'var(--accent-cyan)',   bg: 'rgba(0, 212, 255, 0.12)' };
    case 'CLIMATE':  return { color: 'var(--accent-amber)',  bg: 'rgba(251, 191, 36, 0.12)' };
    case 'ECONOMIC': return { color: 'var(--accent-purple)', bg: 'rgba(167, 139, 250, 0.12)' };
    default:         return { color: 'var(--text-tertiary)', bg: 'rgba(255,255,255,0.08)' };
  }
}

/** 把 API 的 category 字符串映射到内部类别 */
function mapNewsCategory(cat: string): IntelEntry['category'] {
  const upper = cat.toUpperCase();
  if (upper.includes('CONFLICT') || upper.includes('MILITARY') || upper.includes('GEOPOLIT')) return 'CONFLICT';
  if (upper.includes('CYBER') || upper.includes('TECH')) return 'CYBER';
  if (upper.includes('CLIMATE') || upper.includes('WEATHER') || upper.includes('DISASTER')) return 'CLIMATE';
  return 'ECONOMIC';
}

/** 把 API 时间字符串转为 HH:MM:SS 时间戳 */
function formatTimestamp(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    return d.toTimeString().slice(0, 8);
  } catch {
    return '--:--:--';
  }
}

/** 根据严重度推算等级文本 */
function severityFromScore(score: number): 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' {
  if (score >= 85) return 'CRITICAL';
  if (score >= 70) return 'HIGH';
  if (score >= 50) return 'MEDIUM';
  return 'LOW';
}

/** 可点击外部链接组件 — 青色下划线悬停效果 */
function ExtLink({ href, children, className = '', style }: { href: string; children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => {
        e.preventDefault();
        window.open(href, '_blank');
      }}
      className={clsx(
        'cursor-pointer transition-all duration-200',
        'hover:underline hover:decoration-[var(--accent-cyan)] hover:underline-offset-2',
        className
      )}
      style={{ textDecoration: 'none', ...style }}
    >
      {children}
    </a>
  );
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

/* ====== 地图色阶图例组件 ====== */
function MapLegend() {
  const { t } = useLanguage();
  const items = [
    { color: '#ff003c', labelKey: 'worldMonitor.levelCritical', range: '85+' },
    { color: '#ff6b35', labelKey: 'worldMonitor.levelHigh',     range: '70-84' },
    { color: '#fbbf24', labelKey: 'worldMonitor.levelElevated', range: '50-69' },
    { color: '#00d4ff', labelKey: 'worldMonitor.levelModerate', range: '30-49' },
    { color: 'rgba(255,255,255,0.25)', labelKey: 'worldMonitor.levelLow', range: '0-29' },
  ];
  return (
    <div className="flex items-center gap-3 flex-wrap">
      {items.map((it) => (
        <div key={it.labelKey} className="flex items-center gap-1.5">
          <span
            className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
            style={{ background: it.color }}
          />
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
            {t(it.labelKey)} {it.range}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ====== 地图悬停提示组件 ====== */
function MapTooltip({ info }: { info: TooltipInfo | null }) {
  const { t } = useLanguage();
  if (!info) return null;
  const fill = riskScoreToFill(info.score);
  return (
    <div
      className="pointer-events-none fixed z-[9999] px-3 py-2 rounded-lg"
      style={{
        left: info.x + 12,
        top: info.y - 40,
        background: 'rgba(2,2,2,0.92)',
        border: '1px solid rgba(255,255,255,0.15)',
        backdropFilter: 'blur(12px)',
      }}
    >
      <div className="flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ background: fill }}
        />
        <span className="font-display text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
          {info.name}
        </span>
      </div>
      <div className="flex items-center gap-3 mt-1">
        <span className="font-mono text-[10px]" style={{ color: fill }}>
          {t('worldMonitor.riskScore')}: {info.score}
        </span>
        <span
          className="px-1.5 py-0.5 rounded font-mono text-[8px] tracking-wider"
          style={{ background: `${fill}20`, color: fill }}
        >
          {t(info.level)}
        </span>
      </div>
    </div>
  );
}

/* ====== SVG 世界地图热力图组件 ====== */
function WorldHeatmap({ riskScores }: { riskScores: Record<string, number> }) {
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  /** ISO 数字 ID → ISO alpha-3 映射表 */
  const numericToIso3: Record<string, string> = useMemo(() => ({
    '004': 'AFG', '008': 'ALB', '012': 'DZA', '024': 'AGO', '032': 'ARG',
    '036': 'AUS', '040': 'AUT', '050': 'BGD', '056': 'BEL', '068': 'BOL',
    '076': 'BRA', '100': 'BGR', '854': 'BFA', '108': 'BDI', '116': 'KHM',
    '120': 'CMR', '124': 'CAN', '140': 'CAF', '148': 'TCD', '152': 'CHL',
    '156': 'CHN', '170': 'COL', '178': 'COG', '180': 'COD', '188': 'CRI',
    '191': 'HRV', '192': 'CUB', '196': 'CYP', '203': 'CZE', '208': 'DNK',
    '214': 'DOM', '218': 'ECU', '818': 'EGY', '222': 'SLV', '226': 'GNQ',
    '232': 'ERI', '233': 'EST', '231': 'ETH', '246': 'FIN', '250': 'FRA',
    '266': 'GAB', '270': 'GMB', '268': 'GEO', '276': 'DEU', '288': 'GHA',
    '300': 'GRC', '320': 'GTM', '324': 'GIN', '328': 'GUY', '332': 'HTI',
    '340': 'HND', '348': 'HUN', '356': 'IND', '360': 'IDN', '364': 'IRN',
    '368': 'IRQ', '372': 'IRL', '376': 'ISR', '380': 'ITA', '384': 'CIV',
    '388': 'JAM', '392': 'JPN', '400': 'JOR', '398': 'KAZ', '404': 'KEN',
    '408': 'PRK', '410': 'KOR', '414': 'KWT', '417': 'KGZ', '418': 'LAO',
    '428': 'LVA', '422': 'LBN', '426': 'LSO', '430': 'LBR', '434': 'LBY',
    '440': 'LTU', '442': 'LUX', '450': 'MDG', '454': 'MWI', '458': 'MYS',
    '466': 'MLI', '478': 'MRT', '484': 'MEX', '496': 'MNG', '504': 'MAR',
    '508': 'MOZ', '104': 'MMR', '516': 'NAM', '524': 'NPL', '528': 'NLD',
    '554': 'NZL', '558': 'NIC', '562': 'NER', '566': 'NGA', '578': 'NOR',
    '512': 'OMN', '586': 'PAK', '591': 'PAN', '598': 'PNG', '600': 'PRY',
    '604': 'PER', '608': 'PHL', '616': 'POL', '620': 'PRT', '634': 'QAT',
    '642': 'ROU', '643': 'RUS', '646': 'RWA', '682': 'SAU', '686': 'SEN',
    '694': 'SLE', '702': 'SGP', '703': 'SVK', '705': 'SVN', '706': 'SOM',
    '710': 'ZAF', '724': 'ESP', '144': 'LKA', '729': 'SDN', '740': 'SUR',
    '748': 'SWZ', '752': 'SWE', '756': 'CHE', '760': 'SYR', '158': 'TWN',
    '762': 'TJK', '834': 'TZA', '764': 'THA', '768': 'TGO', '780': 'TTO',
    '788': 'TUN', '792': 'TUR', '795': 'TKM', '800': 'UGA', '804': 'UKR',
    '784': 'ARE', '826': 'GBR', '840': 'USA', '858': 'URY', '860': 'UZB',
    '862': 'VEN', '704': 'VNM', '887': 'YEM', '894': 'ZMB', '716': 'ZWE',
  }), []);

  /** 鼠标进入国家区域 — 显示提示 */
  const handleMouseEnter = useCallback(
    (geo: { properties: { name: string }; id: string }, evt: React.MouseEvent) => {
      const iso3 = numericToIso3[geo.id] || '';
      const score = riskScores[iso3];
      if (score !== undefined) {
        setTooltip({
          name: geo.properties.name,
          score,
          level: riskScoreToLevel(score),
          x: evt.clientX,
          y: evt.clientY,
        });
      } else {
        setTooltip({
          name: geo.properties.name,
          score: 0,
          level: 'worldMonitor.noData',
          x: evt.clientX,
          y: evt.clientY,
        });
      }
    },
    [numericToIso3, riskScores]
  );

  /** 鼠标移动 — 跟踪提示位置 */
  const handleMouseMove = useCallback(
    (evt: React.MouseEvent) => {
      setTooltip((prev) =>
        prev ? { ...prev, x: evt.clientX, y: evt.clientY } : null
      );
    },
    []
  );

  /** 鼠标离开 — 隐藏提示 */
  const handleMouseLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  /** 点击国家 — 跳转 worldmonitor.app */
  const handleClick = useCallback(() => {
    window.open('https://worldmonitor.app', '_blank');
  }, []);

  return (
    <div className="relative w-full" style={{ minHeight: 320 }}>
      <MapTooltip info={tooltip} />
      <ComposableMap
        projection="geoEqualEarth"
        projectionConfig={{ scale: 160, center: [0, 0] }}
        width={800}
        height={400}
        style={{
          width: '100%',
          height: 'auto',
          background: 'transparent',
        }}
      >
        <ZoomableGroup center={[10, 20]} zoom={1}>
          <Geographies geography={GEO_URL}>
            {({ geographies }: { geographies: Array<{ rsmKey: string; id: string; properties: { name: string } }> }) =>
              geographies.map((geo) => {
                const iso3 = numericToIso3[geo.id] || '';
                const score = riskScores[iso3];
                const fill = score !== undefined
                  ? riskScoreToFill(score)
                  : 'rgba(255,255,255,0.04)';

                return (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    onMouseEnter={(evt: React.MouseEvent) => handleMouseEnter(geo, evt)}
                    onMouseMove={handleMouseMove}
                    onMouseLeave={handleMouseLeave}
                    onClick={handleClick}
                    style={{
                      default: {
                        fill,
                        stroke: 'rgba(255,255,255,0.15)',
                        strokeWidth: 0.4,
                        outline: 'none',
                        cursor: score !== undefined ? 'pointer' : 'default',
                        transition: 'fill 0.2s ease',
                      },
                      hover: {
                        fill: score !== undefined
                          ? riskScoreToFill(score)
                          : 'rgba(255,255,255,0.1)',
                        stroke: 'rgba(255,255,255,0.4)',
                        strokeWidth: 0.8,
                        outline: 'none',
                        cursor: 'pointer',
                        filter: score !== undefined ? 'brightness(1.3)' : 'none',
                      },
                      pressed: {
                        fill: score !== undefined
                          ? riskScoreToFill(score)
                          : 'rgba(255,255,255,0.06)',
                        stroke: 'rgba(255,255,255,0.3)',
                        strokeWidth: 0.6,
                        outline: 'none',
                      },
                    }}
                  />
                );
              })
            }
          </Geographies>
        </ZoomableGroup>
      </ComposableMap>
    </div>
  );
}

/* ====== 主组件 ====== */

/**
 * 全球监控面板 — Sonic Abyss Bento Grid 布局
 * 12 列 CSS Grid，玻璃卡片 + 终端美学
 * 展示地缘风险、冲突、基础设施状态、气候灾害与情报流
 * 数据来自后端 /api/v1/monitor/risk + /api/v1/monitor/news
 * 每 30 秒自动刷新
 */
export function WorldMonitor() {
  const { t, lang } = useLanguage();
  /* ====== 状态 ====== */
  const [riskList, setRiskList] = useState<RiskApiItem[]>([]);
  const [globalRisk, setGlobalRisk] = useState<{ score: number; severity: string } | null>(null);
  const [intelFeed, setIntelFeed] = useState<IntelEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  /* 扩展监控数据（基础设施/气候/网络安全） */
  const [extData, setExtData] = useState<any>(null);
  const [extLoading, setExtLoading] = useState(true);

  /** 从后端拉取所有数据 */
  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [riskResp, globalResp, newsResp] = await Promise.all([
        clawbotFetchJson<{ risks: RiskApiItem[] }>('/api/v1/monitor/risk'),
        clawbotFetchJson<GlobalRiskApi>('/api/v1/monitor/risk/global'),
        clawbotFetchJson<{ items: NewsApiItem[] }>('/api/v1/monitor/news?category=geopolitics&limit=10'),
      ]);

      /* 国家风险列表 */
      setRiskList(riskResp.risks ?? []);

      /* 全球综合风险分数 */
      setGlobalRisk({
        score: (globalResp.global_score as number | undefined) ?? globalResp.score ?? 0,
        severity: globalResp.severity ?? 'LOW',
      });

      /* 情报日志 — 从新闻条目转换 */
      const entries: IntelEntry[] = (newsResp.items ?? []).map((item, idx) => ({
        id: String(idx + 1),
        timestamp: formatTimestamp(item.published_at),
        category: mapNewsCategory(item.category),
        message: `[${item.source}] ${item.title}`.replace(/&#\d+;/g, (m) => {
          const el = document.createElement('textarea'); el.innerHTML = m; return el.value;
        }),
      }));
      setIntelFeed(entries);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      const friendly = (await import('../../lib/errorMessages')).toFriendlyError(err);
      setError(`${friendly.title}: ${friendly.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  /* 首次加载 + 定时刷新 */
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(fetchData, REFRESH_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  /* 拉取扩展监控数据（基础设施/气候/网络安全） */
  useEffect(() => {
    let cancelled = false;
    const fetchExt = () => {
      setExtLoading(true);
      api.monitorExtended()
        .then((data: any) => { if (!cancelled) { setExtData(data); setExtLoading(false); } })
        .catch(() => { if (!cancelled) { setExtData(null); setExtLoading(false); } });
    };
    fetchExt();
    const extTimer = setInterval(fetchExt, REFRESH_INTERVAL);
    return () => { cancelled = true; clearInterval(extTimer); };
  }, []);

  /* ====== 衍生数据 ====== */

  /** 构建 ISO alpha-3 → 风险分数 映射（供地图使用） */
  const riskScoresMap = useMemo<Record<string, number>>(() => {
    const map: Record<string, number> = {};
    for (const item of riskList) {
      const iso3 = ISO2_TO_ISO3[item.country_code.toUpperCase()];
      if (iso3) {
        map[iso3] = item.composite_score;
      }
    }
    return map;
  }, [riskList]);

  /** 前 8 高风险国家（按分数降序） */
  const topRiskCountries = useMemo<CountryRisk[]>(() => {
    return [...riskList]
      .sort((a, b) => b.composite_score - a.composite_score)
      .slice(0, 8)
      .map((r) => ({
        country: r.country_name,
        code: r.country_code.toUpperCase(),
        score: r.composite_score,
        severity: severityFromScore(r.composite_score),
        change24h: r.change_24h ?? 0,
        link: 'https://worldmonitor.app',
      }));
  }, [riskList]);

  /** 活跃冲突区域（CRITICAL + HIGH，按分数降序取前 5） */
  const conflictZones = useMemo(() => {
    return [...riskList]
      .filter((r) => r.composite_score >= 70)
      .sort((a, b) => b.composite_score - a.composite_score)
      .slice(0, 5)
      .map((r) => ({
        region: r.country_name,
        severity: (r.composite_score >= 85 ? 'CRITICAL' : 'HIGH') as 'CRITICAL' | 'HIGH',
        description: `${t('worldMonitor.riskScore')} ${r.composite_score}，24h ${r.change_24h > 0 ? '+' : ''}${(r.change_24h ?? 0).toFixed(1)}`,
        link: 'https://worldmonitor.app',
      }));
  }, [riskList]);

  /* 全局风险值 */
  const globalScore = globalRisk?.score ?? 0;
  const globalSeverity = (globalRisk?.severity?.toUpperCase() ?? 'LOW') as string;
  const coveredCountries = riskList.length;

  /* ====== 加载/错误状态 ====== */
  if (loading && riskList.length === 0) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <LoadingState message={t('worldMonitor.loadingRiskData')} />
        </div>
      </div>
    );
  }

  if (error && riskList.length === 0) {
    return (
      <div className="h-full overflow-y-auto scroll-container">
        <div className="p-6 max-w-[1440px] mx-auto">
          <ErrorState message={`${t('worldMonitor.loadFailed')}: ${error}`} onRetry={fetchData} />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container">
      <motion.div
        className="grid grid-cols-12 gap-4 p-6 max-w-[1440px] mx-auto auto-rows-min"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {/* ====== 第一行：全球风险分数 (span-4) + SVG 世界地图热力图 (span-8, row-span-2) ====== */}

        {/* 全球综合风险分数卡 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              {t('worldMonitor.globalRiskIndex')}
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              {t('worldMonitor.compositeRiskAssessment')}
            </h3>

            {/* 大数字展示区 */}
            <div className="flex-1 flex flex-col items-center justify-center py-6">
              <div className="relative">
                {/* 外圈脉冲光晕 */}
                <motion.div
                  className="absolute inset-0 rounded-full"
                  style={{
                    background: `radial-gradient(circle, ${severityColor(globalSeverity)}20 0%, transparent 70%)`,
                  }}
                  animate={{ scale: [1, 1.3, 1], opacity: [0.6, 0.2, 0.6] }}
                  transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                />
                <span
                  className="text-metric relative z-10"
                  style={{
                    fontSize: '72px',
                    lineHeight: 1,
                    color: severityColor(globalSeverity),
                  }}
                >
                  {globalScore}
                </span>
              </div>
              <span className="font-mono text-xs mt-2" style={{ color: 'var(--text-tertiary)' }}>
                / 100
              </span>
            </div>

            {/* 严重度标签 + 状态指示 */}
            <div className="flex items-center justify-between">
              <span
                className="px-3 py-1 rounded-full font-mono text-[10px] tracking-wider"
                style={{
                  background: `${severityColor(globalSeverity)}15`,
                  color: severityColor(globalSeverity),
                  border: `1px solid ${severityColor(globalSeverity)}30`,
                }}
              >
                {t(SEVERITY_I18N_KEY[globalSeverity] ?? 'worldMonitor.severityLow')} {t('worldMonitor.risk')}
              </span>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="status-dot-green"
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                  {t('worldMonitor.realtime')}
                </span>
                {lastUpdated && (
                  <>
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>·</span>
                    <Clock size={9} style={{ color: 'var(--text-disabled)' }} />
                    <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      {t('worldMonitor.lastUpdate')} {lastUpdated.toLocaleTimeString(lang === 'en-US' ? 'en-US' : 'zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== SVG 世界地图热力图 — 大卡片 (col-span-8, row-span-2) ====== */}
        <motion.div className="col-span-12 lg:col-span-8 lg:row-span-2" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            {/* 标题栏 */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Map size={16} style={{ color: 'var(--accent-red)' }} />
                <div>
                  <span className="text-label" style={{ color: 'var(--accent-red)' }}>
                    {t('worldMonitor.globalThreatMap')}
                  </span>
                  <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                    {t('worldMonitor.countryRiskHeatmap')}
                  </h3>
                </div>
              </div>
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                {t('worldMonitor.riskOverlay')} · {t('worldMonitor.covering')} {coveredCountries} {t('worldMonitor.countries')}
              </span>
            </div>

            {/* SVG 世界地图 */}
            <div className="flex-1 mt-3 rounded-xl overflow-hidden" style={{ background: 'rgba(0,0,0,0.2)' }}>
              <WorldHeatmap riskScores={riskScoresMap} />
            </div>

            {/* 色阶图例 */}
            <div className="mt-3">
              <MapLegend />
            </div>

            {/* 分隔线 */}
            <div className="my-3" style={{ borderTop: '1px solid var(--glass-border)' }} />

            {/* 高风险国家表格（前 8 国） */}
            <div className="flex-shrink-0">
              {/* 表头 */}
              <div
                className="grid grid-cols-[1fr_80px_100px_80px] gap-2 px-3 py-2 rounded-lg mb-1"
                style={{ background: 'rgba(255,255,255,0.02)' }}
              >
                <span className="text-label" style={{ fontSize: '10px' }}>{t('worldMonitor.country')}</span>
                <span className="text-label text-right" style={{ fontSize: '10px' }}>{t('worldMonitor.score')}</span>
                <span className="text-label text-center" style={{ fontSize: '10px' }}>{t('worldMonitor.severity')}</span>
                <span className="text-label text-right" style={{ fontSize: '10px' }}>{t('worldMonitor.24h')}</span>
              </div>

              {/* 数据行 */}
              {topRiskCountries.map((c, i) => (
                <motion.div
                  key={c.code}
                  className="grid grid-cols-[1fr_80px_100px_80px] gap-2 px-3 py-2.5 rounded-lg transition-colors"
                  style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)' }}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.3 + i * 0.08, duration: 0.3 }}
                >
                  {/* 国家名称 — 可点击链接 */}
                  <div className="flex items-center gap-2">
                    <Globe size={13} style={{ color: severityColor(c.severity), flexShrink: 0 }} />
                    <ExtLink href={c.link} className="flex items-center gap-1.5">
                      <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                        {c.country}
                      </span>
                      <ExternalLink size={9} style={{ color: 'var(--text-disabled)', opacity: 0.6 }} />
                    </ExtLink>
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

                  {/* 严重度徽章 — 中文 */}
                  <div className="flex justify-center">
                    <span
                      className="px-2 py-0.5 rounded-full font-mono text-[10px] tracking-wider"
                      style={{
                        background: `${severityColor(c.severity)}12`,
                        color: severityColor(c.severity),
                        border: `1px solid ${severityColor(c.severity)}25`,
                      }}
                    >
                      {t(SEVERITY_I18N_KEY[c.severity] ?? 'worldMonitor.severityLow')}
                    </span>
                  </div>

                  {/* 24小时变化 */}
                  <div className="flex justify-end items-center">
                    <ChangeIndicator value={c.change24h} />
                  </div>
                </motion.div>
              ))}
            </div>

            {/* 底部数据来源备注 */}
            <div className="flex items-center gap-2 mt-3 pt-3" style={{ borderTop: '1px solid var(--glass-border)' }}>
              <Radio size={12} style={{ color: 'var(--text-disabled)' }} />
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                {t('worldMonitor.autoRefreshNote')} · {t('worldMonitor.source')}:{' '}
                <ExtLink href="https://acleddata.com" className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>ACLED</ExtLink>
                {' / '}
                <ExtLink href="https://worldmonitor.app" className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>WorldMonitor</ExtLink>
                {' / GDELT / SIPRI'}
              </span>
            </div>
          </div>
        </motion.div>

        {/* ====== 第二行左侧（与地图同行）：活跃冲突卡 (span-4) ====== */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-red)' }}>
              {t('worldMonitor.activeConflicts')}
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              {t('worldMonitor.conflictZoneMonitor')}
            </h3>

            {/* 冲突数量大数字 */}
            <div className="flex items-baseline gap-2 mt-4">
              <span className="text-metric" style={{ color: 'var(--accent-red)' }}>
                {conflictZones.length}
              </span>
              <span className="text-label">{t('worldMonitor.activeZones')}</span>
            </div>

            {/* 冲突列表 */}
            <div className="flex flex-col gap-2.5 mt-4 flex-1">
              {conflictZones.length === 0 && (
                <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                  {t('worldMonitor.noHighRisk')}
                </span>
              )}
              {conflictZones.map((zone) => (
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
                      <ExtLink href={zone.link}>
                        <span className="font-mono text-xs font-bold" style={{ color: 'var(--text-primary)' }}>
                          {zone.region}
                        </span>
                      </ExtLink>
                      <span
                        className="px-1.5 py-0.5 rounded font-mono text-[8px] tracking-wider"
                        style={{
                          background: `${severityColor(zone.severity)}12`,
                          color: severityColor(zone.severity),
                        }}
                      >
                        {t(SEVERITY_I18N_KEY[zone.severity] ?? 'worldMonitor.severityLow')}
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

        {/* ====== 第三行：基础设施 (span-4) + 气候灾害 (span-4) + 网络安全 (span-4) ====== */}

        {/* 基础设施状态卡 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              {t('worldMonitor.infrastructure')}
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              {t('worldMonitor.criticalInfraStatus')}
            </h3>

            {/* 数据源状态指示 */}
            <div className="flex items-center gap-1.5">
              {extLoading ? (
                <>
                  <Loader2 size={9} className="animate-spin" style={{ color: 'var(--accent-amber)' }} />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-amber)' }}>{t('worldMonitor.loading')}</span>
                </>
              ) : extData ? (
                <>
                  <motion.span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ background: 'var(--accent-green)' }}
                    animate={{ opacity: [1, 0.4, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>{t('worldMonitor.realtime')}</span>
                </>
              ) : (
                <>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent-red)' }} />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-red)' }}>{t('common.offline')}</span>
                </>
              )}
            </div>

            <div className="flex flex-col gap-4 mt-5 flex-1">
              {/* 互联网中断 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(255, 0, 60, 0.1)' }}>
                    <WifiOff size={15} style={{ color: 'var(--accent-red)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.internetOutage')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.globalOutageEvents')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-red)' }}>{extData?.infrastructure?.internet_outage?.value ?? '—'}</span>
              </div>

              {/* GPS 干扰 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(251, 191, 36, 0.1)' }}>
                    <AlertTriangle size={15} style={{ color: 'var(--accent-amber)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>GPS {t('worldMonitor.jamming')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.navSignalAnomaly')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-amber)' }}>{extData?.infrastructure?.gps_jamming?.value ?? '—'}</span>
              </div>

              {/* 电力网络 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0, 255, 170, 0.1)' }}>
                    <Zap size={15} style={{ color: 'var(--accent-green)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.powerGrid')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.gridStatus')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: ['异常', 'abnormal', 'critical', 'error'].includes(String(extData?.infrastructure?.power_grid?.value ?? '').toLowerCase()) ? 'var(--accent-red)' : 'var(--accent-green)' }}>{extData?.infrastructure?.power_grid?.value ?? '—'}</span>
              </div>

              {/* 海底光缆 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0, 212, 255, 0.1)' }}>
                    <Wifi size={15} style={{ color: 'var(--accent-cyan)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.submarineCable')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.transoceanicLink')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: ['降级', 'degraded', 'warning'].includes(String(extData?.infrastructure?.submarine_cable?.value ?? '').toLowerCase()) ? 'var(--accent-amber)' : 'var(--accent-green)' }}>{extData?.infrastructure?.submarine_cable?.value ?? '—'}</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* 气候与灾害卡 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              {t('worldMonitor.climateDisaster')}
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              {t('worldMonitor.naturalDisasterMonitor')}
            </h3>

            {/* 数据源状态指示 */}
            <div className="flex items-center gap-1.5">
              {extLoading ? (
                <>
                  <Loader2 size={9} className="animate-spin" style={{ color: 'var(--accent-amber)' }} />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-amber)' }}>{t('worldMonitor.loading')}</span>
                </>
              ) : extData ? (
                <>
                  <motion.span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ background: 'var(--accent-green)' }}
                    animate={{ opacity: [1, 0.4, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>{t('worldMonitor.realtime')}</span>
                </>
              ) : (
                <>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent-red)' }} />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-red)' }}>{t('common.offline')}</span>
                </>
              )}
            </div>

            <div className="flex flex-col gap-4 mt-5 flex-1">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(251, 191, 36, 0.1)' }}>
                    <Shield size={15} style={{ color: 'var(--accent-amber)' }} />
                  </div>
                  <div>
                    <ExtLink href="https://earthquake.usgs.gov">
                      <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.seismicActivity')}</span>
                    </ExtLink>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>M4.5+ / 24h</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-amber)' }}>{extData?.climate?.seismic?.value ?? '—'}</span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(255, 0, 60, 0.1)' }}>
                    <Flame size={15} style={{ color: 'var(--accent-red)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.wildfire')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.globalActiveWildfires')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-red)' }}>{extData?.climate?.wildfire?.value ?? '—'}</span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(167, 139, 250, 0.1)' }}>
                    <CloudLightning size={15} style={{ color: 'var(--accent-purple)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.climateAnomaly')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.anomaliesDetected')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-purple)' }}>{extData?.climate?.climate_anomaly?.value ?? '—'}</span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0, 212, 255, 0.1)' }}>
                    <AlertTriangle size={15} style={{ color: 'var(--accent-cyan)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.extremeWeather')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.severeWeatherAlert')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-cyan)' }}>{extData?.climate?.extreme_weather?.value ?? '—'}</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* 网络安全态势卡 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              {t('worldMonitor.cybersecurity')}
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              {t('worldMonitor.cyberThreatPosture')}
            </h3>

            {/* 数据源状态指示 */}
            <div className="flex items-center gap-1.5">
              {extLoading ? (
                <>
                  <Loader2 size={9} className="animate-spin" style={{ color: 'var(--accent-amber)' }} />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-amber)' }}>{t('worldMonitor.loading')}</span>
                </>
              ) : extData ? (
                <>
                  <motion.span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ background: 'var(--accent-green)' }}
                    animate={{ opacity: [1, 0.4, 1] }}
                    transition={{ duration: 2, repeat: Infinity }}
                  />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>{t('worldMonitor.realtime')}</span>
                </>
              ) : (
                <>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--accent-red)' }} />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-red)' }}>{t('common.offline')}</span>
                </>
              )}
            </div>

            <div className="flex flex-col gap-4 mt-5 flex-1">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(255, 0, 60, 0.1)' }}>
                    <Shield size={15} style={{ color: 'var(--accent-red)' }} />
                  </div>
                  <div>
                    <ExtLink href="https://www.cisa.gov/known-exploited-vulnerabilities-catalog">
                      <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.activeExploits')}</span>
                    </ExtLink>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.cisaKev')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-red)' }}>{extData?.cyber?.active_exploits?.value ?? '—'}</span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(251, 191, 36, 0.1)' }}>
                    <Zap size={15} style={{ color: 'var(--accent-amber)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.massiveDdos')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.detected24h')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-amber)' }}>{extData?.cyber?.ddos?.value ?? '—'}</span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(167, 139, 250, 0.1)' }}>
                    <AlertTriangle size={15} style={{ color: 'var(--accent-purple)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.ransomware')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.weeklyDisclosed')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-purple)' }}>{extData?.cyber?.ransomware?.value ?? '—'}</span>
              </div>

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(0, 212, 255, 0.1)' }}>
                    <Terminal size={15} style={{ color: 'var(--accent-cyan)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>{t('worldMonitor.supplyChainAttack')}</span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>{t('worldMonitor.pkgCiPoisoning')}</p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-cyan)' }}>{extData?.cyber?.supply_chain?.value ?? '—'}</span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* ====== 第四行：情报终端流 (span-12) ====== */}
        <motion.div className="col-span-12" variants={cardVariants}>
          <div className="abyss-card p-6">
            {/* 标题栏 — 终端风格 */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Terminal size={14} style={{ color: 'var(--accent-cyan)' }} />
                <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
                  {t('worldMonitor.intelTerminal')}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="status-dot-green"
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                  {t('worldMonitor.liveStream')}
                </span>
              </div>
            </div>

            {/* 终端日志列表 */}
            <div
              className="rounded-xl p-3 max-h-[280px] overflow-y-auto scroll-container"
              style={{ background: 'rgba(0,0,0,0.3)' }}
            >
              {intelFeed.length === 0 && (
                <div className="flex items-center justify-center py-6">
                  <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
                    {t('worldMonitor.noIntelData')}
                  </span>
                </div>
              )}
              {intelFeed.map((entry, i) => {
                const meta = categoryMeta(entry.category);
                const categoryLink: Record<string, string> = {
                  CONFLICT: 'https://acleddata.com',
                  CYBER: 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog',
                  CLIMATE: 'https://earthquake.usgs.gov',
                  ECONOMIC: 'https://worldmonitor.app',
                };
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

                    {/* 类别徽章 — 中文 + 可点击 */}
                    <ExtLink href={categoryLink[entry.category] || '#'} className="flex-shrink-0 mt-0.5">
                      <span
                        className="px-1.5 py-0.5 rounded font-mono text-[10px] tracking-wider"
                        style={{
                          background: meta.bg,
                          color: meta.color,
                          minWidth: '48px',
                          textAlign: 'center',
                          display: 'inline-block',
                        }}
                      >
                        {t(CATEGORY_I18N_KEY[entry.category] ?? '') || entry.category}
                      </span>
                    </ExtLink>

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
                {t('worldMonitor.showingRecent')} {intelFeed.length} {t('worldMonitor.entries')} · {t('worldMonitor.sourceOsint')}
              </span>
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                {t('worldMonitor.autoRefresh30s')}
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
