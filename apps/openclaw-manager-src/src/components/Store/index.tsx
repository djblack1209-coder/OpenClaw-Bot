import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
} from 'lucide-react';

import { GlassCard } from '../shared';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../ui/dialog';

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
  installed: boolean;
  featured?: boolean;
}

/**
 * 模拟插件数据（后续会接入 Evolution 引擎）
 */
const MOCK_PLUGINS: Plugin[] = [
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
 * 插件商店主组件
 */
export function Store() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<CategoryId>('featured');
  const [selectedPlugin, setSelectedPlugin] = useState<Plugin | null>(null);
  const [installedPlugins, setInstalledPlugins] = useState<Set<string>>(
    new Set(MOCK_PLUGINS.filter((p) => p.installed).map((p) => p.id))
  );

  /**
   * 过滤插件列表
   */
  const filteredPlugins = useMemo(() => {
    let result = MOCK_PLUGINS;

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
  }, [searchQuery, selectedCategory, installedPlugins]);

  /**
   * 安装插件
   */
  const handleInstall = (plugin: Plugin) => {
    toast.loading('正在安装...', { id: plugin.id });
    setTimeout(() => {
      setInstalledPlugins((prev) => new Set(prev).add(plugin.id));
      toast.success('安装成功！', { id: plugin.id });
    }, 1500);
  };

  /**
   * 卸载插件
   */
  const handleUninstall = (plugin: Plugin) => {
    if (!confirm(`确定要卸载「${plugin.name}」吗？`)) return;
    
    toast.loading('正在卸载...', { id: plugin.id });
    setTimeout(() => {
      setInstalledPlugins((prev) => {
        const next = new Set(prev);
        next.delete(plugin.id);
        return next;
      });
      toast.success('已卸载', { id: plugin.id });
      if (selectedPlugin?.id === plugin.id) {
        setSelectedPlugin(null);
      }
    }, 800);
  };

  return (
    <div className="h-full flex flex-col">
      {/* 搜索栏 */}
      <div className="px-6 pt-6 pb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
          <Input
            type="text"
            placeholder="搜索插件..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 h-10 bg-white/5 border-white/10 text-white placeholder:text-gray-500"
          />
        </div>
      </div>

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

      {/* 插件网格 */}
      <div className="flex-1 px-6 pb-6 overflow-y-auto">
        {filteredPlugins.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <Package size={48} className="text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">没有找到相关插件</p>
              <p className="text-sm text-gray-500 mt-1">试试其他关键词或分类</p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <AnimatePresence mode="popLayout">
              {filteredPlugins.map((plugin) => (
                <PluginCard
                  key={plugin.id}
                  plugin={plugin}
                  installed={installedPlugins.has(plugin.id)}
                  onInstall={() => handleInstall(plugin)}
                  onUninstall={() => handleUninstall(plugin)}
                  onClick={() => setSelectedPlugin(plugin)}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* 插件详情弹窗 */}
      <Dialog open={!!selectedPlugin} onOpenChange={() => setSelectedPlugin(null)}>
        {selectedPlugin && (
          <DialogContent className="max-w-2xl bg-[#1a1a1a] border-white/10">
            <DialogHeader>
              <div className="flex items-start gap-4">
                <div className="text-5xl">{selectedPlugin.icon}</div>
                <div className="flex-1">
                  <DialogTitle className="text-xl text-white mb-2">
                    {selectedPlugin.name}
                  </DialogTitle>
                  <div className="flex items-center gap-3 text-sm text-gray-400">
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
            </DialogHeader>

            <DialogDescription className="text-gray-300 leading-relaxed">
              {selectedPlugin.fullDescription}
            </DialogDescription>

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

            <DialogFooter className="flex-row gap-2">
              {installedPlugins.has(selectedPlugin.id) ? (
                <>
                  <Button
                    variant="outline"
                    onClick={() => handleUninstall(selectedPlugin)}
                    className="flex-1"
                  >
                    卸载插件
                  </Button>
                  <Button className="flex-1 bg-[var(--oc-brand)] hover:bg-[var(--oc-brand)]/80">
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
                >
                  <Download size={16} />
                  安装插件
                </Button>
              )}
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}

/**
 * 插件卡片组件
 */
interface PluginCardProps {
  plugin: Plugin;
  installed: boolean;
  onInstall: () => void;
  onUninstall: () => void;
  onClick: () => void;
}

function PluginCard({ plugin, installed, onInstall, onUninstall, onClick }: PluginCardProps) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.2 }}
    >
      <GlassCard
        className="p-4 cursor-pointer hover:border-[var(--oc-brand)]/30 transition-colors"
        onClick={onClick}
      >
        <div className="flex items-start gap-3 mb-3">
          <div className="text-3xl">{plugin.icon}</div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-white mb-1 truncate">{plugin.name}</h3>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <div className="flex items-center gap-1">
                <Star size={12} className="text-yellow-500 fill-yellow-500" />
                <span>{(plugin.stars / 1000).toFixed(1)}k</span>
              </div>
              <Badge variant="outline" className="text-[10px] h-4 px-1.5">
                {CATEGORIES.find((c) => c.id === plugin.category[0])?.label}
              </Badge>
            </div>
          </div>
        </div>

        <p className="text-xs text-gray-400 mb-3 line-clamp-2">{plugin.description}</p>

        <div onClick={(e) => e.stopPropagation()}>
          {installed ? (
            <Button
              size="sm"
              variant="outline"
              className="w-full text-[var(--oc-success)] border-[var(--oc-success)]/30 hover:bg-[var(--oc-success)]/10"
              onClick={onUninstall}
            >
              <Check size={14} />
              已安装
            </Button>
          ) : (
            <Button
              size="sm"
              className="w-full bg-[var(--oc-brand)] hover:bg-[var(--oc-brand)]/80"
              onClick={onInstall}
            >
              <Download size={14} />
              安装
            </Button>
          )}
        </div>
      </GlassCard>
    </motion.div>
  );
}
