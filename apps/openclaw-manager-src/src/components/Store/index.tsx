import { useState, useMemo, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import { toast } from 'sonner';
import {
  Search,
  Download,
  Check,
  Star,
  Package,
  ExternalLink,
  Sparkles,
  TrendingUp,
  ShoppingCart,
  MessageSquare,
  Home,
  Code,
  RefreshCw,
  Loader2,
  Radar,
  Zap,
  Clock,
  AlertCircle,
} from 'lucide-react';

import { GlassCard } from '../shared';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '../ui/sheet';
import { Progress } from '../ui/progress';
import { api, clawbotFetch } from '../../lib/tauri';
import { useAppStore } from '@/stores/appStore';
import { createLogger } from '@/lib/logger';

const logger = createLogger('Store');

/**
 * 插件分类定义
 */
const CATEGORIES = [
  { id: 'featured', label: '精选推荐', icon: Sparkles },
  { id: 'ai', label: 'AI工具', icon: Sparkles },
  { id: 'trading', label: '投资交易', icon: TrendingUp },
  { id: 'ecommerce', label: '电商', icon: ShoppingCart },
  { id: 'social', label: '社媒', icon: MessageSquare },
  { id: 'life', label: '生活', icon: Home },
  { id: 'dev', label: '开发者', icon: Code },
  { id: 'installed', label: '已安装', icon: Package },
] as const;

type CategoryId = (typeof CATEGORIES)[number]['id'];

/**
 * 插件数据类型
 */
interface Plugin {
  id: string;
  name: string;
  icon: string;
  category: CategoryId[];
  stars: number;
  description: string;
  fullDescription: string;
  author: string;
  features: string[];
  installed?: boolean;
  featured?: boolean;
}

/**
 * 预置插件目录 — 已知的高质量集成能力
 * 安装状态由 localStorage 管理，不在此硬编码
 * 真实 star 数据由 Evolution 引擎补充
 */
const CURATED_PLUGINS: Plugin[] = [
  {
    id: 'comfyui',
    name: 'ComfyUI 图片生成',
    icon: '🎨',
    category: ['ai', 'featured'],
    stars: 10200,
    description: '让AI帮你生成精美图片',
    fullDescription: '基于 ComfyUI 的强大图片生成能力，支持文生图、图生图、风格迁移等多种模式。无需复杂配置，一句话就能生成专业级图片。',
    author: 'OpenClaw Team',
    features: [
      '支持多种 AI 模型（SDXL、Flux、DALL-E 等）',
      '一句话描述即可生成图片',
      '支持图片风格迁移和编辑',
      '批量生成和高清放大',
    ],
    installed: true,
    featured: true,
  },
  {
    id: 'whisper',
    name: 'Whisper 语音识别',
    icon: '🎤',
    category: ['ai'],
    stars: 8500,
    description: '高精度语音转文字，支持多语言',
    fullDescription: '基于 OpenAI Whisper 模型，提供业界领先的语音识别能力。支持 100+ 种语言，准确率高达 95%。',
    author: 'OpenClaw Team',
    features: [
      '支持 100+ 种语言识别',
      '实时语音转文字',
      '自动标点和分段',
      '支持音频文件批量处理',
    ],
    installed: false,
  },
  {
    id: 'tavily',
    name: 'Tavily 智能搜索',
    icon: '🔍',
    category: ['ai', 'featured'],
    stars: 6800,
    description: 'AI 驱动的深度网页搜索',
    fullDescription: '专为 AI 优化的搜索引擎，能够深度理解查询意图，返回最相关的结构化信息。比传统搜索更智能。',
    author: 'Tavily',
    features: [
      '深度理解搜索意图',
      '返回结构化数据',
      '自动过滤低质量内容',
      '支持实时新闻和学术搜索',
    ],
    installed: true,
    featured: true,
  },
  {
    id: 'jina',
    name: 'Jina 网页读取',
    icon: '📄',
    category: ['ai'],
    stars: 5200,
    description: '一键提取网页核心内容',
    fullDescription: '智能提取网页正文、图片、表格等核心内容，自动过滤广告和无关信息。支持 PDF、文档等多种格式。',
    author: 'Jina AI',
    features: [
      '智能提取网页正文',
      '自动过滤广告和导航栏',
      '支持 PDF 和文档解析',
      '保留格式和结构',
    ],
    installed: false,
  },
  {
    id: 'freqtrade',
    name: 'Freqtrade 量化交易',
    icon: '📈',
    category: ['trading', 'featured'],
    stars: 15600,
    description: '开源量化交易框架，支持回测和实盘',
    fullDescription: '全球最流行的开源量化交易框架，支持多种交易所、策略回测、实盘交易。内置风控和监控系统。',
    author: 'Freqtrade Team',
    features: [
      '支持 Binance、OKX 等主流交易所',
      '内置 100+ 种技术指标',
      '策略回测和参数优化',
      '实盘交易和风控管理',
    ],
    installed: false,
  },
  {
    id: 'vectorbt',
    name: 'VectorBT 回测引擎',
    icon: '📊',
    category: ['trading'],
    stars: 3400,
    description: '超快速的向量化回测框架',
    fullDescription: '基于 NumPy 的向量化回测引擎，速度比传统回测快 100 倍。支持复杂策略和组合优化。',
    author: 'VectorBT',
    features: [
      '向量化计算，速度极快',
      '支持多资产组合回测',
      '内置性能分析和可视化',
      '支持机器学习策略',
    ],
    installed: false,
  },
  {
    id: 'yfinance',
    name: 'yfinance 行情数据',
    icon: '💹',
    category: ['trading'],
    stars: 12800,
    description: '免费获取全球股票、加密货币行情',
    fullDescription: '从 Yahoo Finance 获取全球股票、ETF、加密货币的实时和历史行情数据。完全免费，无需 API Key。',
    author: 'Ran Aroussi',
    features: [
      '支持全球股票和加密货币',
      '实时行情和历史数据',
      '财务报表和公司信息',
      '完全免费，无需注册',
    ],
    installed: true,
  },
  {
    id: 'ibkr',
    name: 'IBKR 券商接口',
    icon: '🏦',
    category: ['trading'],
    stars: 2100,
    description: '连接盈透证券，全球市场交易',
    fullDescription: '连接盈透证券（Interactive Brokers），支持全球 150+ 个市场的股票、期权、期货交易。',
    author: 'OpenClaw Team',
    features: [
      '支持全球 150+ 个市场',
      '股票、期权、期货交易',
      '实时行情和账户管理',
      '低佣金和融资利率',
    ],
    installed: false,
  },
  {
    id: 'xianyu-ai',
    name: '闲鱼 AI 客服',
    icon: '🛍️',
    category: ['ecommerce', 'featured'],
    stars: 4200,
    description: '自动回复买家消息，提升转化率',
    fullDescription: 'AI 自动回复闲鱼买家咨询，支持议价、催单、售后等场景。24 小时在线，提升 3 倍转化率。',
    author: 'OpenClaw Team',
    features: [
      'AI 自动回复买家消息',
      '支持议价和催单场景',
      '自动发货和物流跟踪',
      '数据分析和优化建议',
    ],
    installed: false,
  },
  {
    id: 'price-compare',
    name: '商品比价助手',
    icon: '💰',
    category: ['ecommerce'],
    stars: 1800,
    description: '全网比价，找到最低价',
    fullDescription: '一键比价淘宝、京东、拼多多等平台的同款商品，自动找到最低价和优惠券。',
    author: 'OpenClaw Team',
    features: [
      '支持淘宝、京东、拼多多等平台',
      '自动查找优惠券',
      '价格历史趋势分析',
      '降价提醒',
    ],
    installed: false,
  },
  {
    id: 'mediacrawler',
    name: 'MediaCrawler 采集',
    icon: '📱',
    category: ['social'],
    stars: 9200,
    description: '采集小红书、抖音、B站内容',
    fullDescription: '一键采集小红书、抖音、B站的笔记、视频、评论等数据。支持关键词搜索、用户主页、话题采集。',
    author: 'NanmiCoder',
    features: [
      '支持小红书、抖音、B站等平台',
      '采集笔记、视频、评论',
      '关键词和话题搜索',
      '数据导出和分析',
    ],
    installed: true,
  },
  {
    id: 'xhs-publish',
    name: '小红书发布助手',
    icon: '📝',
    category: ['social'],
    stars: 3600,
    description: '一键发布笔记到小红书',
    fullDescription: '自动发布图文笔记到小红书，支持定时发布、批量发布、数据分析。提升 10 倍运营效率。',
    author: 'OpenClaw Team',
    features: [
      '一键发布图文笔记',
      '定时发布和批量发布',
      '自动添加话题和标签',
      '数据分析和优化建议',
    ],
    installed: false,
  },
  {
    id: 'browser-use',
    name: 'browser-use 浏览器控制',
    icon: '🌐',
    category: ['dev', 'featured'],
    stars: 7800,
    description: 'AI 控制浏览器，自动化任何操作',
    fullDescription: '让 AI 像人一样操作浏览器，自动填表、点击、截图、爬虫。支持 Chrome 和 Firefox。',
    author: 'browser-use',
    features: [
      'AI 自动操作浏览器',
      '支持复杂交互和表单',
      '自动截图和数据提取',
      '支持无头模式和代理',
    ],
    installed: false,
  },
  {
    id: 'drissionpage',
    name: 'DrissionPage 爬虫',
    icon: '🕷️',
    category: ['dev'],
    stars: 6500,
    description: '比 Selenium 更快的浏览器自动化',
    fullDescription: '结合了 requests 和 Selenium 的优点，速度快、功能强、易用。支持动态网页和反爬虫。',
    author: 'g1879',
    features: [
      '比 Selenium 快 10 倍',
      '支持动态网页和 AJAX',
      '自动处理反爬虫',
      '简洁的 API 设计',
    ],
    installed: false,
  },
  {
    id: 'mcp',
    name: 'MCP 协议支持',
    icon: '🔌',
    category: ['dev'],
    stars: 4100,
    description: '接入 Model Context Protocol 生态',
    fullDescription: '支持 Anthropic 的 MCP 协议，让 AI 助手能够调用任何 MCP 服务器。扩展无限可能。',
    author: 'Anthropic',
    features: [
      '支持 MCP 协议标准',
      '接入 MCP 服务器生态',
      '自动发现和调用工具',
      '支持本地和远程服务器',
    ],
    installed: true,
  },
];

/**
 * 将 Evolution 提案的模块/分类映射到商店分类
 */
function mapProposalCategory(moduleOrCategory?: string): CategoryId[] {
  if (!moduleOrCategory) return ['dev'];
  const lower = moduleOrCategory.toLowerCase();
  if (lower.includes('trading') || lower.includes('invest') || lower.includes('finance'))
    return ['trading'];
  if (lower.includes('social') || lower.includes('media'))
    return ['social'];
  if (lower.includes('ecommerce') || lower.includes('shop') || lower.includes('commerce'))
    return ['ecommerce'];
  if (lower.includes('ai') || lower.includes('llm') || lower.includes('model'))
    return ['ai'];
  if (lower.includes('life') || lower.includes('util'))
    return ['life'];
  return ['dev'];
}

/**
 * 将 Evolution 提案转换为 Plugin 格式
 */
function proposalToPlugin(p: Record<string, unknown>): Plugin {
  const repo = (p.repo || p.repo_name || '') as string;
  return {
    id: (p.id || p.proposal_id || repo || '') as string,
    name: (p.name || repo?.split('/').pop() || 'Unknown') as string,
    icon: (p.icon as string) || '🔌',
    category: mapProposalCategory(
      (p.target_module || p.module || p.category) as string | undefined
    ),
    stars: ((p.stars || p.stargazers_count || 0) as number),
    description: (p.summary || p.description || '') as string,
    fullDescription: (p.details || p.description || '') as string,
    author: (p.author || (repo ? repo.split('/')[0] : '') || 'Community') as string,
    features: (p.features as string[]) || [],
    installed: p.status === 'integrated',
    featured: ((p.value_score || p.score || 0) as number) > 80,
  };
}

/**
 * Evolution 引擎统计数据（展示用）
 */
interface EvolutionStats {
  totalProposals: number;
  lastScan: string | null;
  approved: number;
  pending: number;
}

/**
 * 格式化最后扫描时间为相对时间
 */
function formatLastScan(timeStr: string): string {
  try {
    const date = new Date(timeStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} 小时前`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay} 天前`;
  } catch {
    return timeStr;
  }
}

/**
 * 插件商店主组件
 */
export function Store() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<CategoryId>('featured');
  const [selectedPlugin, setSelectedPlugin] = useState<Plugin | null>(null);
  const [installedPlugins, setInstalledPlugins] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem('openclaw-installed-plugins');
      if (saved) return new Set(JSON.parse(saved));
    } catch {}
    return new Set(CURATED_PLUGINS.filter((p) => p.installed).map((p) => p.id));
  });
  const [installingPlugin, setInstallingPlugin] = useState<string | null>(null);
  const [installProgress, setInstallProgress] = useState(0);

  // Evolution 引擎状态
  const [evolutionPlugins, setEvolutionPlugins] = useState<Plugin[]>([]);
  const [evolutionStats, setEvolutionStats] = useState<EvolutionStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  /** 标记是否为本地缓存数据（Evolution API 不可达时） */
  const [usingLocalData, setUsingLocalData] = useState(false);

  // Persist installed plugins to localStorage on every change
  useEffect(() => {
    localStorage.setItem('openclaw-installed-plugins', JSON.stringify([...installedPlugins]));
  }, [installedPlugins]);

  /**
   * 合并 Evolution + 预置目录插件，按 id 去重
   * Evolution 真实数据优先，预置目录填补空白
   */
  const allPlugins = useMemo(() => {
    const seen = new Set<string>();
    const merged: Plugin[] = [];
    // Evolution 真实数据优先
    for (const p of evolutionPlugins) {
      if (!seen.has(p.id)) {
        seen.add(p.id);
        merged.push(p);
      }
    }
    // 预置目录填补空白
    for (const p of CURATED_PLUGINS) {
      if (!seen.has(p.id)) {
        seen.add(p.id);
        merged.push(p);
      }
    }
    return merged;
  }, [evolutionPlugins]);

  /**
   * 从 Evolution 引擎加载提案和统计数据
   */
  const fetchEvolutionData = useCallback(async () => {
    setLoading(true);
    try {
      const [proposalsResp, statsResp] = await Promise.allSettled([
        api.evolutionProposals('approved', 50),
        api.evolutionStats(),
      ]);

      // 处理提案数据
      if (proposalsResp.status === 'fulfilled') {
        const data = proposalsResp.value;
        const rawProposals: Record<string, unknown>[] =
          (data as any)?.proposals ?? (data as any)?.data ?? (Array.isArray(data) ? data : []);
        const transformed = rawProposals.map(proposalToPlugin);
        setEvolutionPlugins(transformed);

        // 标记已集成的插件
        const integratedIds = transformed.filter((p) => p.installed).map((p) => p.id);
        if (integratedIds.length > 0) {
          setInstalledPlugins((prev) => {
            const next = new Set(prev);
            integratedIds.forEach((id) => next.add(id));
            return next;
          });
        }
      }

      // 处理统计数据
      if (statsResp.status === 'fulfilled') {
        const stats = statsResp.value as Record<string, unknown>;
        setEvolutionStats({
          totalProposals: (stats.total_proposals ?? stats.proposals_count ?? 0) as number,
          lastScan: (stats.last_scan ?? stats.last_scan_at ?? stats.last_scan_time ?? null) as string | null,
          approved: (stats.approved ?? (stats.by_status as any)?.approved ?? 0) as number,
          pending: (stats.pending ?? (stats.by_status as any)?.pending ?? 0) as number,
        });
      }
    } catch (err) {
      // 展示本地缓存数据降级提示
      setUsingLocalData(true);
      logger.warn('Evolution 数据加载失败，使用本地数据', err);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * 触发扫描并刷新
   */
  const handleScan = useCallback(async () => {
    setScanning(true);
    try {
      await api.evolutionScan();
      toast.success('扫描已触发，正在发现新插件...');
      // 等待一小段时间让后端处理完
      setTimeout(() => {
        fetchEvolutionData().finally(() => setScanning(false));
      }, 2000);
    } catch (err) {
      toast.error('扫描触发失败');
      setScanning(false);
    }
  }, [fetchEvolutionData]);

  /**
   * 刷新数据
   */
  const handleRefresh = useCallback(async () => {
    toast.loading('正在刷新...', { id: 'store-refresh' });
    await fetchEvolutionData();
    toast.success('已刷新', { id: 'store-refresh' });
  }, [fetchEvolutionData]);

  // 组件挂载时加载 Evolution 数据
  useEffect(() => {
    fetchEvolutionData();
  }, [fetchEvolutionData]);

  /**
   * 过滤插件列表
   */
  const filteredPlugins = useMemo(() => {
    let result = allPlugins;

    // 分类筛选
    if (selectedCategory === 'installed') {
      result = result.filter((p) => installedPlugins.has(p.id));
    } else if (selectedCategory === 'featured') {
      result = result.filter((p) => p.featured);
    } else {
      result = result.filter((p) => p.category.includes(selectedCategory));
    }

    // 搜索筛选
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter(
        (p) =>
          p.name.toLowerCase().includes(query) ||
          p.description.toLowerCase().includes(query) ||
          p.fullDescription.toLowerCase().includes(query)
      );
    }

    return result;
  }, [searchQuery, selectedCategory, installedPlugins, allPlugins]);

  /**
   * 安装插件（带进度条动画）
   */
  const handleInstall = async (plugin: Plugin) => {
    setInstallingPlugin(plugin.id);
    setInstallProgress(0);
    
    const toastId = plugin.id;
    toast.loading('正在安装...', { id: toastId });
    
    try {
      // 模拟安装进度
      const progressInterval = setInterval(() => {
        setInstallProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 100);

      // Try to call the evolution API to mark as approved/integrated
      await clawbotFetch(`/api/v1/evolution/proposals/${plugin.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'integrated' }),
      }).catch(() => {}); // silently fail if not an evolution plugin

      clearInterval(progressInterval);
      setInstallProgress(100);
      
      setTimeout(() => {
        setInstalledPlugins((prev) => new Set(prev).add(plugin.id));
        setInstallingPlugin(null);
        setInstallProgress(0);
        toast.success('安装成功！', { id: toastId });
      }, 300);
    } catch {
      setInstallingPlugin(null);
      setInstallProgress(0);
      toast.error('安装失败', { id: toastId });
    }
  };

  /**
   * 卸载插件
   */
  const handleUninstall = async (plugin: Plugin) => {
    const toastId = plugin.id;
    toast.loading('正在卸载...', { id: toastId });
    try {
      setInstalledPlugins((prev) => {
        const next = new Set(prev);
        next.delete(plugin.id);
        return next;
      });
      toast.success('已卸载', { id: toastId });
      if (selectedPlugin?.id === plugin.id) {
        setSelectedPlugin(null);
      }
    } catch {
      toast.error('卸载失败', { id: toastId });
    }
  };

  return (
    <div className="h-full flex flex-col bg-[var(--bg-primary)]">
      {/* 本地数据降级提示 */}
      {usingLocalData && (
        <div className="mx-6 mt-4 px-3 py-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-xs text-yellow-400 flex items-center gap-2">
          <AlertCircle size={14} />
          当前展示为本地缓存数据，后端 Evolution API 不可达
        </div>
      )}
      {/* 搜索栏 + 刷新按钮 */}
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
            <Input
              type="text"
              placeholder="搜索插件..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 h-10 bg-white/5 border-white/10 text-white placeholder:text-gray-500"
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={loading}
            className="h-10 px-3 border-white/10 text-gray-400 hover:text-white hover:bg-white/10"
          >
            {loading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <RefreshCw size={16} />
            )}
            刷新
          </Button>
        </div>
      </div>

      {/* Evolution 引擎状态卡片 */}
      {evolutionStats && (
        <div className="px-6 pb-4">
          <GlassCard className="p-4 border-[var(--oc-brand)]/20 bg-[var(--oc-brand)]/5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-[var(--oc-brand)]/20 flex items-center justify-center">
                  <Radar size={20} className="text-[var(--oc-brand)]" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    Evolution 引擎
                    <Badge variant="outline" className="text-[10px] h-4 px-1.5 text-[var(--oc-brand)] border-[var(--oc-brand)]/30">
                      在线
                    </Badge>
                  </h3>
                  <div className="flex items-center gap-4 text-xs text-gray-400 mt-0.5">
                    <span className="flex items-center gap-1">
                      <Zap size={12} />
                      已扫描 {evolutionStats.totalProposals} 个提案
                    </span>
                    {evolutionStats.lastScan && (
                      <span className="flex items-center gap-1">
                        <Clock size={12} />
                        {formatLastScan(evolutionStats.lastScan)}
                      </span>
                    )}
                    <span>
                      ✅ {evolutionStats.approved} 已批准
                    </span>
                    <span>
                      ⏳ {evolutionStats.pending} 待审核
                    </span>
                  </div>
                </div>
              </div>
              <Button
                size="sm"
                onClick={handleScan}
                disabled={scanning}
                className="bg-[var(--oc-brand)] hover:bg-[var(--oc-brand)]/80"
              >
                {scanning ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Radar size={14} />
                )}
                发现新插件
              </Button>
            </div>
          </GlassCard>
        </div>
      )}

      {/* 分类标签 */}
      <div className="px-6 pb-4">
        <div className="flex gap-2 overflow-x-auto scrollbar-hide">
          {CATEGORIES.map((cat) => {
            const Icon = cat.icon;
            const isActive = selectedCategory === cat.id;
            return (
              <motion.button
                key={cat.id}
                onClick={() => setSelectedCategory(cat.id)}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-all',
                  isActive
                    ? 'bg-[var(--oc-brand)] text-white'
                    : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-gray-300'
                )}
                whileTap={{ scale: 0.95 }}
              >
                <Icon size={14} />
                {cat.label}
              </motion.button>
            );
          })}
        </div>
      </div>

      {/* 精选横幅区 */}
      {selectedCategory === 'featured' && (
        <div className="px-6 pb-6">
          <h2 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
            <Sparkles size={18} className="text-[var(--oc-brand)]" />
            精选推荐
          </h2>
          <div className="flex gap-4 overflow-x-auto scrollbar-hide pb-2">
            {filteredPlugins.slice(0, 3).map((plugin) => (
              <FeaturedCard
                key={plugin.id}
                plugin={plugin}
                installed={installedPlugins.has(plugin.id)}
                installing={installingPlugin === plugin.id}
                installProgress={installProgress}
                onInstall={() => handleInstall(plugin)}
                onClick={() => setSelectedPlugin(plugin)}
              />
            ))}
          </div>
        </div>
      )}

      {/* 插件网格 - 4列布局 */}
      <div className="flex-1 px-6 pb-6 overflow-y-auto">
        {loading && evolutionPlugins.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <Loader2 size={36} className="text-[var(--oc-brand)] mx-auto mb-3 animate-spin" />
              <p className="text-gray-400">正在加载插件...</p>
              <p className="text-sm text-gray-500 mt-1">正在连接 Evolution 引擎</p>
            </div>
          </div>
        ) : filteredPlugins.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <Package size={48} className="text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">没有找到相关插件</p>
              <p className="text-sm text-gray-500 mt-1">试试其他关键词或分类</p>
            </div>
          </div>
        ) : (
          <>
            {selectedCategory !== 'featured' && (
              <h2 className="text-base font-semibold text-white mb-4">
                所有插件
              </h2>
            )}
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {(selectedCategory === 'featured' ? filteredPlugins.slice(3) : filteredPlugins).map((plugin) => (
                <PluginCard
                  key={plugin.id}
                  plugin={plugin}
                  installed={installedPlugins.has(plugin.id)}
                  installing={installingPlugin === plugin.id}
                  installProgress={installProgress}
                  onInstall={() => handleInstall(plugin)}
                  onClick={() => setSelectedPlugin(plugin)}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* 插件详情侧边栏 */}
      <Sheet open={!!selectedPlugin} onOpenChange={() => setSelectedPlugin(null)}>
        {selectedPlugin && (
          <SheetContent className="w-full sm:max-w-lg">
            <SheetHeader>
              <div className="flex items-start gap-4">
                <div className="text-5xl">{selectedPlugin.icon}</div>
                <div className="flex-1">
                  <SheetTitle>{selectedPlugin.name}</SheetTitle>
                  <div className="flex items-center gap-3 text-sm text-gray-400 mt-2">
                    <div className="flex items-center gap-1">
                      <Star size={14} className="text-yellow-500 fill-yellow-500" />
                      <span>{(selectedPlugin.stars / 1000).toFixed(1)}k</span>
                    </div>
                    <span>•</span>
                    <span>{selectedPlugin.author}</span>
                    <span>•</span>
                    <Badge variant="outline" className="text-xs">
                      {CATEGORIES.find((c) => c.id === selectedPlugin.category[0])?.label}
                    </Badge>
                  </div>
                </div>
              </div>
            </SheetHeader>

            <div className="flex-1 overflow-y-auto px-6 py-4">
              <SheetDescription className="text-gray-300 leading-relaxed mb-6">
                {selectedPlugin.fullDescription}
              </SheetDescription>

              <div className="space-y-2">
                <h4 className="text-sm font-medium text-white">功能特性</h4>
                <ul className="space-y-1.5">
                  {selectedPlugin.features.map((feature, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-400">
                      <Check size={16} className="text-[var(--oc-success)] mt-0.5 shrink-0" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <SheetFooter className="flex-row gap-2">
              {installedPlugins.has(selectedPlugin.id) ? (
                <>
                  <Button
                    variant="outline"
                    onClick={() => handleUninstall(selectedPlugin)}
                    className="flex-1"
                  >
                    卸载插件
                  </Button>
                  <Button
                    className="flex-1 bg-[var(--oc-brand)] hover:bg-[var(--oc-brand)]/80"
                    onClick={() => {
                      setSelectedPlugin(null);
                      useAppStore.getState().setCurrentPage('assistant');
                    }}
                  >
                    <ExternalLink size={16} />
                    在 AI 助手中使用
                  </Button>
                </>
              ) : (
                <Button
                  onClick={() => {
                    handleInstall(selectedPlugin);
                    setSelectedPlugin(null);
                  }}
                  className="flex-1 bg-[var(--oc-brand)] hover:bg-[var(--oc-brand)]/80"
                  disabled={installingPlugin === selectedPlugin.id}
                >
                  {installingPlugin === selectedPlugin.id ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      安装中...
                    </>
                  ) : (
                    <>
                      <Download size={16} />
                      安装插件
                    </>
                  )}
                </Button>
              )}
            </SheetFooter>
          </SheetContent>
        )}
      </Sheet>
    </div>
  );
}

/**
 * 精选卡片组件 - 大尺寸横向滚动卡片
 */
interface FeaturedCardProps {
  plugin: Plugin;
  installed: boolean;
  installing: boolean;
  installProgress: number;
  onInstall: () => void;
  onClick: () => void;
}

function FeaturedCard({ plugin, installed, installing, installProgress, onInstall, onClick }: FeaturedCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="min-w-[320px] max-w-[320px]"
    >
      <GlassCard
        className="p-5 cursor-pointer hover:border-[var(--oc-brand)]/40 transition-all hover:shadow-lg hover:shadow-[var(--oc-brand)]/10"
        onClick={onClick}
      >
        <div className="flex items-start gap-4 mb-4">
          <div className="text-5xl">{plugin.icon}</div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-bold text-white mb-1 truncate">{plugin.name}</h3>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <div className="flex items-center gap-1">
                <Star size={12} className="text-yellow-500 fill-yellow-500" />
                <span>{(plugin.stars / 1000).toFixed(1)}k</span>
              </div>
              <Badge variant="outline" className="text-[10px] h-4 px-1.5 bg-[var(--oc-brand)]/10 text-[var(--oc-brand)] border-[var(--oc-brand)]/30">
                精选
              </Badge>
            </div>
          </div>
        </div>

        <p className="text-sm text-gray-300 mb-4 line-clamp-2 leading-relaxed">{plugin.description}</p>

        <div onClick={(e) => e.stopPropagation()}>
          {installed ? (
            <Button
              size="sm"
              variant="outline"
              className="w-full text-[var(--oc-success)] border-[var(--oc-success)]/30 hover:bg-[var(--oc-success)]/10"
              disabled
            >
              <Check size={14} />
              已安装
            </Button>
          ) : installing ? (
            <div className="space-y-2">
              <Progress value={installProgress} max={100} />
              <p className="text-xs text-center text-gray-400">安装中 {installProgress}%</p>
            </div>
          ) : (
            <Button
              size="sm"
              className="w-full bg-[var(--oc-brand)] hover:bg-[var(--oc-brand)]/80"
              onClick={onInstall}
            >
              <Download size={14} />
              安装插件
            </Button>
          )}
        </div>
      </GlassCard>
    </motion.div>
  );
}

/**
 * 插件卡片组件 - 标准网格卡片（200×180px）
 */
interface PluginCardProps {
  plugin: Plugin;
  installed: boolean;
  installing: boolean;
  installProgress: number;
  onInstall: () => void;
  onClick: () => void;
}

function PluginCard({ plugin, installed, installing, installProgress, onInstall, onClick }: PluginCardProps) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.2 }}
    >
      <GlassCard
        className="p-3 cursor-pointer hover:border-[var(--oc-brand)]/30 transition-colors h-[180px] flex flex-col"
        onClick={onClick}
      >
        <div className="flex items-start gap-2 mb-2">
          <div className="text-2xl">{plugin.icon}</div>
          <div className="flex-1 min-w-0">
            <h3 className="text-xs font-semibold text-white mb-0.5 truncate">{plugin.name}</h3>
            <div className="flex items-center gap-1 text-[10px] text-gray-400">
              <Star size={10} className="text-yellow-500 fill-yellow-500" />
              <span>{(plugin.stars / 1000).toFixed(1)}k</span>
            </div>
          </div>
        </div>

        <p className="text-[11px] text-gray-400 mb-auto line-clamp-3 leading-relaxed">{plugin.description}</p>

        <div onClick={(e) => e.stopPropagation()} className="mt-2">
          {installed ? (
            <Button
              size="sm"
              variant="outline"
              className="w-full h-7 text-xs text-[var(--oc-success)] border-[var(--oc-success)]/30 hover:bg-[var(--oc-success)]/10"
              disabled
            >
              <Check size={12} />
              已安装
            </Button>
          ) : installing ? (
            <div className="space-y-1">
              <Progress value={installProgress} max={100} className="h-1" />
              <p className="text-[10px] text-center text-gray-400">{installProgress}%</p>
            </div>
          ) : (
            <Button
              size="sm"
              className="w-full h-7 text-xs bg-[var(--oc-brand)] hover:bg-[var(--oc-brand)]/80"
              onClick={onInstall}
            >
              <Download size={12} />
              安装
            </Button>
          )}
        </div>
      </GlassCard>
    </motion.div>
  );
}
