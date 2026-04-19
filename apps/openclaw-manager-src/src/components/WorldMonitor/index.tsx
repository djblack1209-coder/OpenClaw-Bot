import { useState, useCallback, useMemo } from 'react';
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
} from 'lucide-react';

/* ====== TopoJSON 地图源 — Natural Earth 110m 分辨率 ====== */
const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json';

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
  country: string;        // 中文国家名
  code: string;           // ISO alpha-2 国家代码
  score: number;          // 风险分数 0-100
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  change24h: number;      // 24小时变化（正数=上升，负数=下降）
  link: string;           // 外部链接地址
}

/** 冲突区域 */
interface ConflictZone {
  region: string;         // 中文区域名
  severity: 'HIGH' | 'CRITICAL';
  description: string;    // 中文描述
  link: string;           // 外部链接地址
}

/** 情报日志条目 */
interface IntelEntry {
  id: string;
  timestamp: string;
  category: 'CONFLICT' | 'CYBER' | 'CLIMATE' | 'ECONOMIC';
  message: string;        // 中文消息
}

/** 地图悬停提示信息 */
interface TooltipInfo {
  name: string;           // 中文国家名
  score: number;          // 风险分数
  level: string;          // 中文等级
  x: number;              // 鼠标 X 坐标
  y: number;              // 鼠标 Y 坐标
}

/* ====== 严重度中文映射 ====== */
const SEVERITY_CN: Record<string, string> = {
  CRITICAL: '危急',
  HIGH: '高',
  MEDIUM: '中',
  LOW: '低',
};

/** 情报类别中文映射 */
const CATEGORY_CN: Record<string, string> = {
  CONFLICT: '冲突',
  CYBER: '网络',
  CLIMATE: '气候',
  ECONOMIC: '经济',
};

/** ISO alpha-3 → 中文国家名映射 */
const ISO3_TO_CN: Record<string, string> = {
  UKR: '乌克兰', ISR: '以色列', MMR: '缅甸', SDN: '苏丹', YEM: '也门',
  SOM: '索马里', AFG: '阿富汗', SYR: '叙利亚', RUS: '俄罗斯', CHN: '中国',
  USA: '美国', IRN: '伊朗', PRK: '朝鲜', PAK: '巴基斯坦', IRQ: '伊拉克',
  LBY: '利比亚', NGA: '尼日利亚', COD: '刚果(金)', ETH: '埃塞俄比亚', MLI: '马里',
  MEX: '墨西哥', VEN: '委内瑞拉', COL: '哥伦比亚', IND: '印度', TWN: '台湾',
  PHL: '菲律宾', EGY: '埃及', LBN: '黎巴嫩', HTI: '海地', BFA: '布基纳法索',
};

/* ====== 国家风险分数表（ISO alpha-3 → 分数） ====== */
const COUNTRY_RISK_SCORES: Record<string, number> = {
  UKR: 94, ISR: 88, MMR: 79, SDN: 76, YEM: 71,
  SOM: 68, AFG: 65, SYR: 63, RUS: 58, CHN: 42,
  USA: 28, IRN: 72, PRK: 60, PAK: 55, IRQ: 67,
  LBY: 62, NGA: 59, COD: 70, ETH: 57, MLI: 66,
  MEX: 48, VEN: 53, COL: 45, IND: 38, TWN: 35,
  PHL: 40, EGY: 44, LBN: 61, HTI: 73, BFA: 69,
};

/* ====== 模拟数据 ====== */

/** 全球综合风险分数 */
const GLOBAL_RISK_SCORE = 62;
const GLOBAL_RISK_SEVERITY: 'LOW' | 'MEDIUM' | 'HIGH' = 'MEDIUM';

/** 前 8 高风险国家 */
const TOP_RISK_COUNTRIES: CountryRisk[] = [
  { country: '乌克兰',      code: 'UA', score: 94, severity: 'CRITICAL', change24h: 2.1,  link: 'https://acleddata.com' },
  { country: '以色列',      code: 'IL', score: 88, severity: 'CRITICAL', change24h: -1.3, link: 'https://acleddata.com' },
  { country: '缅甸',        code: 'MM', score: 79, severity: 'HIGH',     change24h: 0.5,  link: 'https://worldmonitor.app' },
  { country: '苏丹',        code: 'SD', score: 76, severity: 'HIGH',     change24h: 3.8,  link: 'https://acleddata.com' },
  { country: '也门',        code: 'YE', score: 71, severity: 'HIGH',     change24h: -0.2, link: 'https://acleddata.com' },
  { country: '索马里',      code: 'SO', score: 68, severity: 'HIGH',     change24h: 1.1,  link: 'https://acleddata.com' },
  { country: '阿富汗',      code: 'AF', score: 65, severity: 'HIGH',     change24h: -0.8, link: 'https://worldmonitor.app' },
  { country: '叙利亚',      code: 'SY', score: 63, severity: 'MEDIUM',   change24h: 0.3,  link: 'https://acleddata.com' },
];

/** 活跃冲突区域 */
const CONFLICT_ZONES: ConflictZone[] = [
  { region: '东欧 — 俄乌前线',   severity: 'CRITICAL', description: '俄乌全面冲突持续，扎波罗热和赫尔松方向交火密集', link: 'https://acleddata.com' },
  { region: '中东 — 加沙地区',   severity: 'CRITICAL', description: '加沙人道主义危机加剧，红海航运安全受胁', link: 'https://acleddata.com' },
  { region: '东非 — 苏丹内战',   severity: 'HIGH',     description: '苏丹快速支援部队与政府军交战扩大化', link: 'https://acleddata.com' },
];

/** 情报日志流（全中文） */
const INTEL_FEED: IntelEntry[] = [
  { id: '1',  timestamp: '14:32:08', category: 'CONFLICT',  message: '[乌克兰] 扎波罗热方向检测到新一轮炮击活动，预计影响平民疏散路线' },
  { id: '2',  timestamp: '14:28:41', category: 'CYBER',     message: '[全球] Cloudflare 报告亚太地区 DDoS 攻击流量激增 340%，多家金融机构受影响' },
  { id: '3',  timestamp: '14:25:15', category: 'ECONOMIC',  message: '[中国] 人民币离岸汇率突破 7.28 关口，央行释放稳定信号，市场情绪谨慎' },
  { id: '4',  timestamp: '14:21:33', category: 'CLIMATE',   message: '[日本] 气象厅发布九州地区暴雨特别警报，24小时降水量超 300mm' },
  { id: '5',  timestamp: '14:18:02', category: 'CONFLICT',  message: '[苏丹] 快速支援部队控制北达尔富尔首府，联合国呼吁紧急人道主义通道' },
  { id: '6',  timestamp: '14:14:47', category: 'CYBER',     message: '[美国] CISA 发布关键基础设施漏洞通告 CVE-2026-3891，CVSS 评分 9.8' },
  { id: '7',  timestamp: '14:10:22', category: 'ECONOMIC',  message: '[欧盟] 欧洲央行维持利率不变，但暗示第三季度可能降息 25 个基点' },
  { id: '8',  timestamp: '14:06:59', category: 'CLIMATE',   message: '[加拿大] 不列颠哥伦比亚省 3 处山火失控，过火面积超 12,000 公顷' },
  { id: '9',  timestamp: '14:03:11', category: 'CONFLICT',  message: '[缅甸] 民族抵抗力量在掸邦北部推进，控制 2 个关键据点，军政府调派增援' },
  { id: '10', timestamp: '13:58:44', category: 'CYBER',     message: '[俄罗斯] 多家俄罗斯银行遭受供应链攻击，支付系统中断约 2 小时' },
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

/** 根据风险分数返回填充颜色（地图热力色阶） */
function riskScoreToFill(score: number): string {
  if (score >= 85) return '#ff003c';                // 危急 — 红色
  if (score >= 70) return '#ff6b35';                // 高风险 — 橙色
  if (score >= 50) return '#fbbf24';                // 升高 — 琥珀色
  if (score >= 30) return '#00d4ff';                // 中等 — 青色
  return 'rgba(255,255,255,0.08)';                  // 低/无数据 — 暗色
}

/** 根据风险分数返回中文等级标签 */
function riskScoreToLevel(score: number): string {
  if (score >= 85) return '危急';
  if (score >= 70) return '高';
  if (score >= 50) return '升高';
  if (score >= 30) return '中等';
  return '低';
}

/** 根据情报类别返回对应颜色和背景色 */
function categoryMeta(category: IntelEntry['category']): { color: string; bg: string } {
  switch (category) {
    case 'CONFLICT': return { color: 'var(--accent-red)',    bg: 'rgba(255, 0, 60, 0.12)' };
    case 'CYBER':    return { color: 'var(--accent-cyan)',   bg: 'rgba(0, 212, 255, 0.12)' };
    case 'CLIMATE':  return { color: 'var(--accent-amber)',  bg: 'rgba(251, 191, 36, 0.12)' };
    case 'ECONOMIC': return { color: 'var(--accent-purple)', bg: 'rgba(167, 139, 250, 0.12)' };
  }
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
  /* 色阶条目：颜色 + 中文标签 + 分数范围 */
  const items = [
    { color: '#ff003c', label: '危急', range: '85+' },
    { color: '#ff6b35', label: '高',   range: '70-84' },
    { color: '#fbbf24', label: '升高', range: '50-69' },
    { color: '#00d4ff', label: '中等', range: '30-49' },
    { color: 'rgba(255,255,255,0.25)', label: '低', range: '0-29' },
  ];
  return (
    <div className="flex items-center gap-3 flex-wrap">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-1.5">
          <span
            className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
            style={{ background: it.color }}
          />
          <span className="font-mono text-[9px]" style={{ color: 'var(--text-tertiary)' }}>
            {it.label} {it.range}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ====== 地图悬停提示组件 ====== */
function MapTooltip({ info }: { info: TooltipInfo | null }) {
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
          风险分: {info.score}
        </span>
        <span
          className="px-1.5 py-0.5 rounded font-mono text-[8px] tracking-wider"
          style={{ background: `${fill}20`, color: fill }}
        >
          {info.level}
        </span>
      </div>
    </div>
  );
}

/* ====== SVG 世界地图热力图组件 ====== */
function WorldHeatmap() {
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  /**
   * 从 TopoJSON geography 的 properties 中提取 ISO alpha-3 代码
   * world-atlas@2 的 countries-110m.json 不直接提供 ISO_A3，
   * 但提供了 name 字段。我们用一个数字 ID → ISO alpha-3 的映射表来匹配。
   * 参考：https://github.com/topojson/world-atlas 的 ID 是 ISO 3166-1 数字代码
   */
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
      const score = COUNTRY_RISK_SCORES[iso3];
      if (score !== undefined) {
        const cnName = ISO3_TO_CN[iso3] || geo.properties.name;
        setTooltip({
          name: cnName,
          score,
          level: riskScoreToLevel(score),
          x: evt.clientX,
          y: evt.clientY,
        });
      } else {
        /* 无数据的国家也显示名称 */
        setTooltip({
          name: geo.properties.name,
          score: 0,
          level: '无数据',
          x: evt.clientX,
          y: evt.clientY,
        });
      }
    },
    [numericToIso3]
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
      {/* 悬停提示浮层 */}
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
                /* 通过数字 ID 查找 ISO alpha-3 代码 */
                const iso3 = numericToIso3[geo.id] || '';
                const score = COUNTRY_RISK_SCORES[iso3];
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
 * 第一行：全球风险分数 (span-4) + SVG 世界地图热力图 (span-8, row-span-2)
 * 第二行：活跃冲突 (span-4)（与地图同行）
 * 第三行：基础设施 + 气候灾害 + 网络安全（各 span-4）
 * 第四行：情报终端流 (span-12)
 * 所有文本标签使用中文，国家名和区域名可点击跳转外部源
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
        {/* ====== 第一行：全球风险分数 (span-4) + SVG 世界地图热力图 (span-8, row-span-2) ====== */}

        {/* 全球综合风险分数卡 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              全球风险指数
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              综合风险评估
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
                className="px-3 py-1 rounded-full font-mono text-[10px] tracking-wider"
                style={{
                  background: `${severityColor(GLOBAL_RISK_SEVERITY)}15`,
                  color: severityColor(GLOBAL_RISK_SEVERITY),
                  border: `1px solid ${severityColor(GLOBAL_RISK_SEVERITY)}30`,
                }}
              >
                {SEVERITY_CN[GLOBAL_RISK_SEVERITY]} 风险
              </span>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="status-dot-green"
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                  实时
                </span>
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
                    全球威胁态势图
                  </span>
                  <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
                    国家风险热力图
                  </h3>
                </div>
              </div>
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                风险叠加 · 覆盖 30 国
              </span>
            </div>

            {/* SVG 世界地图 */}
            <div className="flex-1 mt-3 rounded-xl overflow-hidden" style={{ background: 'rgba(0,0,0,0.2)' }}>
              <WorldHeatmap />
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
                <span className="text-label" style={{ fontSize: '10px' }}>国家</span>
                <span className="text-label text-right" style={{ fontSize: '10px' }}>分数</span>
                <span className="text-label text-center" style={{ fontSize: '10px' }}>严重度</span>
                <span className="text-label text-right" style={{ fontSize: '10px' }}>24小时</span>
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
                      className="px-2 py-0.5 rounded-full font-mono text-[9px] tracking-wider"
                      style={{
                        background: `${severityColor(c.severity)}12`,
                        color: severityColor(c.severity),
                        border: `1px solid ${severityColor(c.severity)}25`,
                      }}
                    >
                      {SEVERITY_CN[c.severity]}
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
                数据每 15 分钟更新 · 来源:{' '}
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
              活跃冲突
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              冲突区监控
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
                      {/* 区域名 — 可点击链接 */}
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
                        {SEVERITY_CN[zone.severity]}
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
              基础设施
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              关键设施状态
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
                      全球断网事件
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
                      导航信号异常区域
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
                      电网运行状态
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="status-dot-green" />
                  <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                    稳定
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
                      跨洋通信链路
                    </p>
                  </div>
                </div>
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-amber)' }}>
                  2 条降级
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* 气候与灾害卡 */}
        <motion.div className="col-span-12 md:col-span-6 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-amber)' }}>
              气候与灾害
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              自然灾害监测
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
                    <ExtLink href="https://earthquake.usgs.gov">
                      <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                        地震活动
                      </span>
                    </ExtLink>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      M5.0+ / 24小时
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
                      全球活跃山火
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
                      检测到的异常数
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
                      恶劣天气预警
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

        {/* 网络安全态势卡 */}
        <motion.div className="col-span-12 lg:col-span-4" variants={cardVariants}>
          <div className="abyss-card p-6 h-full flex flex-col">
            <span className="text-label" style={{ color: 'var(--accent-cyan)' }}>
              网络安全
            </span>
            <h3 className="font-display text-lg font-bold mt-1" style={{ color: 'var(--text-primary)' }}>
              赛博威胁态势
            </h3>

            <div className="flex flex-col gap-4 mt-5 flex-1">
              {/* 活跃漏洞 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(255, 0, 60, 0.1)' }}
                  >
                    <Shield size={15} style={{ color: 'var(--accent-red)' }} />
                  </div>
                  <div>
                    <ExtLink href="https://www.cisa.gov/known-exploited-vulnerabilities-catalog">
                      <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                        活跃漏洞利用
                      </span>
                    </ExtLink>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      CISA 已知利用漏洞
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-red)' }}>
                  6
                </span>
              </div>

              {/* DDoS 攻击 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(251, 191, 36, 0.1)' }}
                  >
                    <Zap size={15} style={{ color: 'var(--accent-amber)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      大规模 DDoS
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      24小时内检测
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-amber)' }}>
                  23
                </span>
              </div>

              {/* 勒索攻击 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(167, 139, 250, 0.1)' }}
                  >
                    <AlertTriangle size={15} style={{ color: 'var(--accent-purple)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      勒索软件事件
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      本周公开披露
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-purple)' }}>
                  4
                </span>
              </div>

              {/* 供应链攻击 */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center"
                    style={{ background: 'rgba(0, 212, 255, 0.1)' }}
                  >
                    <Terminal size={15} style={{ color: 'var(--accent-cyan)' }} />
                  </div>
                  <div>
                    <span className="font-mono text-xs" style={{ color: 'var(--text-primary)' }}>
                      供应链攻击
                    </span>
                    <p className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                      包管理器 / CI 投毒
                    </p>
                  </div>
                </div>
                <span className="text-metric" style={{ fontSize: '20px', color: 'var(--accent-cyan)' }}>
                  2
                </span>
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
                  情报终端
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <motion.span
                  className="status-dot-green"
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                />
                <span className="font-mono text-[10px]" style={{ color: 'var(--accent-green)' }}>
                  实时流
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
                /* 根据类别选择外部链接 */
                const categoryLink: Record<IntelEntry['category'], string> = {
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
                    <ExtLink href={categoryLink[entry.category]} className="flex-shrink-0 mt-0.5">
                      <span
                        className="px-1.5 py-0.5 rounded font-mono text-[9px] tracking-wider"
                        style={{
                          background: meta.bg,
                          color: meta.color,
                          minWidth: '48px',
                          textAlign: 'center',
                          display: 'inline-block',
                        }}
                      >
                        {CATEGORY_CN[entry.category]}
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
                显示最近 {INTEL_FEED.length} 条 · 来源: 开源情报 / GDELT / ACLED / CVE
              </span>
              <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
                自动刷新 60秒
              </span>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
}
