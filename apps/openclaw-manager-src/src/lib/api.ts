import { clawbotFetch } from './tauri-core';
import * as ipc from './tauri-ipc';

// API 封装（带日志）
export const api = {
  // ── 服务管理 ──
  getServiceStatus: ipc.getServiceStatus,
  startService: ipc.startService,
  stopService: ipc.stopService,
  restartService: ipc.restartService,
  getLogs: ipc.getLogs,

  // ── 系统信息 ──
  getSystemInfo: ipc.getSystemInfo,
  checkOpenclawInstalled: ipc.checkOpenclawInstalled,
  getOpenclawVersion: ipc.getOpenclawVersion,

  // ── 配置管理 ──
  getConfig: ipc.getConfig,
  saveConfig: ipc.saveConfig,
  getEnvValue: ipc.getEnvValue,
  saveEnvValue: ipc.saveEnvValue,
  getProjectContext: ipc.getProjectContext,
  getAppSettings: ipc.getAppSettings,
  saveAppSettings: ipc.saveAppSettings,
  openMacOSFullDiskAccessSettings: ipc.openMacOSFullDiskAccessSettings,

  // ── AI Provider（旧版兼容） ──
  getAIProviders: ipc.getAIProviders,

  // ── AI 配置（新版） ──
  getOfficialProviders: ipc.getOfficialProviders,
  getAIConfig: ipc.getAIConfig,
  saveProvider: ipc.saveProvider,
  deleteProvider: ipc.deleteProvider,
  setPrimaryModel: ipc.setPrimaryModel,
  addAvailableModel: ipc.addAvailableModel,
  removeAvailableModel: ipc.removeAvailableModel,

  // ── 渠道 ──
  getChannelsConfig: ipc.getChannelsConfig,
  saveChannelConfig: ipc.saveChannelConfig,

  // ── 诊断测试 ──
  runDoctor: ipc.runDoctor,
  testAIConnection: ipc.testAIConnection,
  testChannel: ipc.testChannel,

  // ── 总控中心（OpenClaw + ClawBot） ──
  getManagedServicesStatus: ipc.getManagedServicesStatus,
  controlManagedService: ipc.controlManagedService,
  controlAllManagedServices: ipc.controlAllManagedServices,
  getClawbotRuntimeConfig: ipc.getClawbotRuntimeConfig,
  getClawbotBotMatrix: ipc.getClawbotBotMatrix,
  getOpenclawUsageSnapshot: ipc.getOpenclawUsageSnapshot,
  saveClawbotRuntimeConfig: ipc.saveClawbotRuntimeConfig,
  getManagedServiceLogs: ipc.getManagedServiceLogs,
  getManagedEndpointsStatus: ipc.getManagedEndpointsStatus,
  getSkillsStatus: ipc.getSkillsStatus,

  // ── ClawBot 系统 ──
  clawbotPing: ipc.clawbotPing,
  clawbotStatus: ipc.clawbotStatus,

  // ── 交易系统 ──
  clawbotTradingSystem: ipc.clawbotTradingSystem,
  clawbotTradingPositions: ipc.clawbotTradingPositions,
  clawbotTradingPnl: ipc.clawbotTradingPnl,
  clawbotTradingSignals: ipc.clawbotTradingSignals,
  clawbotTradingVote: ipc.clawbotTradingVote,

  // ── 社媒浏览器状态 ──
  clawbotSocialBrowserStatus: ipc.clawbotSocialBrowserStatus,

  // ── 交易状态 ──
  clawbotTradingStatus: ipc.clawbotTradingStatus,

  // ── 社媒运营 ──
  clawbotSocialStatus: ipc.clawbotSocialStatus,
  clawbotSocialTopics: ipc.clawbotSocialTopics,
  clawbotSocialCompose: ipc.clawbotSocialCompose,
  clawbotSocialPublish: ipc.clawbotSocialPublish,
  clawbotSocialResearch: ipc.clawbotSocialResearch,
  clawbotSocialMetrics: ipc.clawbotSocialMetrics,
  clawbotSocialPersonas: ipc.clawbotSocialPersonas,
  clawbotSocialCalendar: ipc.clawbotSocialCalendar,

  // ── 社媒自动驾驶 ──
  clawbotAutopilotStatus: ipc.clawbotAutopilotStatus,
  clawbotAutopilotStart: ipc.clawbotAutopilotStart,
  clawbotAutopilotStop: ipc.clawbotAutopilotStop,
  clawbotAutopilotTrigger: ipc.clawbotAutopilotTrigger,

  // ── 社媒草稿管理 ──
  clawbotSocialDrafts: ipc.clawbotSocialDrafts,
  clawbotSocialDraftUpdate: ipc.clawbotSocialDraftUpdate,
  clawbotSocialDraftDelete: ipc.clawbotSocialDraftDelete,
  clawbotSocialDraftPublish: ipc.clawbotSocialDraftPublish,

  // ── 图像生成 ──
  clawbotGenerateImage: ipc.clawbotGenerateImage,
  clawbotGeneratePersonaPhoto: ipc.clawbotGeneratePersonaPhoto,

  // ── 记忆系统 ──
  clawbotMemorySearch: ipc.clawbotMemorySearch,
  clawbotMemoryDelete: ipc.clawbotMemoryDelete,
  clawbotMemoryUpdate: ipc.clawbotMemoryUpdate,
  clawbotMemoryStats: ipc.clawbotMemoryStats,

  // ── API 池 ──
  clawbotPoolStats: ipc.clawbotPoolStats,

  // ── 自进化系统 ──
  clawbotEvolutionScan: ipc.clawbotEvolutionScan,
  clawbotEvolutionProposals: ipc.clawbotEvolutionProposals,
  clawbotEvolutionGaps: ipc.clawbotEvolutionGaps,
  clawbotEvolutionStats: ipc.clawbotEvolutionStats,
  clawbotEvolutionUpdateProposal: ipc.clawbotEvolutionUpdateProposal,

  // ── 比价引擎 ──
  clawbotShoppingCompare: ipc.clawbotShoppingCompare,

  // ── OMEGA v2.0 ──
  omegaStatus: ipc.omegaStatus,
  omegaCost: ipc.omegaCost,
  omegaEvents: ipc.omegaEvents,
  omegaAudit: ipc.omegaAudit,
  omegaTasks: ipc.omegaTasks,
  omegaProcess: ipc.omegaProcess,
  omegaInvestmentTeam: ipc.omegaInvestmentTeam,
  omegaInvestmentAnalyze: ipc.omegaInvestmentAnalyze,
  omegaGenerateImage: ipc.omegaGenerateImage,
  omegaGenerateVideo: ipc.omegaGenerateVideo,
  omegaMediaModels: ipc.omegaMediaModels,

  // ── MCP 插件进程管理 ──
  startMcpPlugin: ipc.startMcpPlugin,
  stopMcpPlugin: ipc.stopMcpPlugin,
  getMcpPluginStatus: ipc.getMcpPluginStatus,

  // ══════════════════════════════════════════════
  //  New-API 网关管理 (HTTP)
  // ══════════════════════════════════════════════

  // 网关运行状态
  newApiStatus: () => clawbotFetch('/api/v1/newapi/status'),

  // 渠道列表
  newApiChannels: () => clawbotFetch('/api/v1/newapi/channels'),

  // 令牌列表
  newApiTokens: () => clawbotFetch('/api/v1/newapi/tokens'),

  // 创建渠道
  newApiCreateChannel: (data: {
    name: string;
    type?: number;
    key?: string;
    base_url?: string;
    models?: string;
    group?: string;
  }) =>
    clawbotFetch('/api/v1/newapi/channels', {
      method: 'POST',
      body: JSON.stringify(data),
      headers: { 'Content-Type': 'application/json' },
    }),

  // 更新渠道
  newApiUpdateChannel: (channelId: number, data: Record<string, unknown>) =>
    clawbotFetch(`/api/v1/newapi/channels/${channelId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
      headers: { 'Content-Type': 'application/json' },
    }),

  // 删除渠道
  newApiDeleteChannel: (channelId: number) =>
    clawbotFetch(`/api/v1/newapi/channels/${channelId}`, {
      method: 'DELETE',
    }),

  // 切换渠道启用/禁用状态
  newApiToggleChannel: (channelId: number) =>
    clawbotFetch(`/api/v1/newapi/channels/${channelId}/status`, {
      method: 'POST',
    }),

  // 删除令牌
  newApiDeleteToken: (tokenId: number) =>
    clawbotFetch(`/api/v1/newapi/tokens/${tokenId}`, {
      method: 'DELETE',
    }),

  // ══════════════════════════════════════════════
  //  今日简报 (Daily Brief)
  // ══════════════════════════════════════════════

  /** 获取首页今日简报数据 — 聚合各模块指标 */
  dailyBrief: () =>
    clawbotFetch('/api/v1/system/daily-brief').then(r => r.json()),

  // ══════════════════════════════════════════════
  //  通知中心 (Notifications)
  // ══════════════════════════════════════════════

  /** 获取通知列表 */
  notifications: (params?: { limit?: number; category?: string; unread_only?: boolean }) => {
    const sp = new URLSearchParams();
    if (params?.limit) sp.set('limit', String(params.limit));
    if (params?.category) sp.set('category', params.category);
    if (params?.unread_only) sp.set('unread_only', 'true');
    const qs = sp.toString();
    return clawbotFetch(`/api/v1/system/notifications${qs ? '?' + qs : ''}`).then(r => r.json());
  },

  /** 标记单条通知为已读 */
  markNotificationRead: (notificationId: string) =>
    clawbotFetch(`/api/v1/system/notifications/${notificationId}/read`, {
      method: 'POST',
    }).then(r => r.json()),

  /** 标记所有通知为已读 */
  markAllNotificationsRead: () =>
    clawbotFetch('/api/v1/system/notifications/read-all', {
      method: 'POST',
    }).then(r => r.json()),

  // ══════════════════════════════════════════════
  //  持仓摘要 (Portfolio Summary)
  // ══════════════════════════════════════════════

  /** 获取持仓聚合摘要 — 总资产/盈亏/持仓列表/权重 */
  portfolioSummary: () =>
    clawbotFetch('/api/v1/trading/portfolio-summary').then(r => r.json()),

  // ══════════════════════════════════════════════
  //  服务管理 (Services)
  // ══════════════════════════════════════════════

  /** 获取所有服务状态 */
  services: () =>
    clawbotFetch('/api/v1/system/services').then(r => r.json()),

  /** 获取单个服务状态 */
  serviceStatus: (serviceId: string) =>
    clawbotFetch(`/api/v1/system/services/${serviceId}`).then(r => r.json()),

  // ══════════════════════════════════════════════
  //  AI 会话 (Conversation)
  // ══════════════════════════════════════════════

  /** 获取会话列表 */
  conversationSessions: (limit: number = 50) =>
    clawbotFetch(`/api/v1/conversation/sessions?limit=${limit}`).then(r => r.json()),

  /** 创建新会话 */
  conversationCreate: (title: string = '新对话') =>
    clawbotFetch(`/api/v1/conversation/sessions?title=${encodeURIComponent(title)}`, {
      method: 'POST',
    }).then(r => r.json()),

  /** 获取会话详情（含所有消息） */
  conversationGet: (sessionId: string) =>
    clawbotFetch(`/api/v1/conversation/sessions/${sessionId}`).then(r => r.json()),

  /** 删除会话 */
  conversationDelete: (sessionId: string) =>
    clawbotFetch(`/api/v1/conversation/sessions/${sessionId}`, {
      method: 'DELETE',
    }).then(r => r.json()),

  /** 发送消息（返回 SSE 流式 Response 对象，调用方需自行处理 EventSource） */
  conversationSend: (sessionId: string, message: string) =>
    clawbotFetch(`/api/v1/conversation/sessions/${sessionId}/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    }),

  // ══════════════════════════════════════════════
  //  闲鱼扫码登录 (Xianyu QR Login)
  // ══════════════════════════════════════════════

  /** 生成闲鱼扫码登录二维码 */
  xianyuGenerateQR: async () => {
    const resp = await clawbotFetch('/api/v1/xianyu/qr/generate', { method: 'POST' });
    return resp.json();
  },

  /** 查询闲鱼二维码扫码状态 */
  xianyuQRStatus: async () => {
    const resp = await clawbotFetch('/api/v1/xianyu/qr/status');
    return resp.json();
  },

  /** 获取闲鱼最近对话列表 */
  xianyuConversations: async (limit: number = 20) => {
    const resp = await clawbotFetch(`/api/v1/xianyu/conversations?limit=${limit}`);
    return resp.json();
  },

  // ══════════════════════════════════════════════
  //  服务控制 (Service Control)
  // ══════════════════════════════════════════════

  /** 启动指定服务 */
  serviceStart: async (serviceId: string) => {
    const resp = await clawbotFetch(`/api/v1/system/services/${serviceId}/start`, { method: 'POST' });
    return resp.json();
  },

  /** 停止指定服务 */
  serviceStop: async (serviceId: string) => {
    const resp = await clawbotFetch(`/api/v1/system/services/${serviceId}/stop`, { method: 'POST' });
    return resp.json();
  },

  // ══════════════════════════════════════════════
  //  交易操作 (Trading Actions)
  // ══════════════════════════════════════════════

  /** 卖出持仓 */
  tradingSell: async (symbol: string, quantity: number, orderType: string = 'MKT') => {
    const resp = await clawbotFetch('/api/v1/trading/sell', {
      method: 'POST',
      body: JSON.stringify({ symbol, quantity, order_type: orderType }),
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`卖出请求失败 (HTTP ${resp.status}): ${text || '未知错误'}`);
    }
    return resp.json();
  },

  // ══════════════════════════════════════════════
  //  自选股监控 (Watchlist)
  // ══════════════════════════════════════════════

  /** 获取自选股列表 */
  watchlist: async () => {
    const resp = await clawbotFetch('/api/v1/trading/watchlist');
    return resp.json();
  },

  /** 添加自选股 */
  watchlistAdd: async (symbol: string, targetPrice: number, direction: 'above' | 'below') => {
    const resp = await clawbotFetch('/api/v1/trading/watchlist', {
      method: 'POST',
      body: JSON.stringify({ symbol, target_price: targetPrice, direction }),
    });
    return resp.json();
  },

  /** 删除自选股 */
  watchlistRemove: async (symbol: string) => {
    const resp = await clawbotFetch(`/api/v1/trading/watchlist/${symbol}`, { method: 'DELETE' });
    return resp.json();
  },

  // ══════════════════════════════════════════════
  //  Evolution 引擎 (HTTP 降级)
  // ══════════════════════════════════════════════

  /** 获取进化提案列表（HTTP） */
  evolutionProposals: async (status?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (limit) params.set('limit', String(limit));
    const resp = await clawbotFetch(`/api/v1/evolution/proposals?${params}`);
    return resp.json();
  },

  /** 获取进化统计数据（HTTP） */
  evolutionStats: async () => {
    const resp = await clawbotFetch('/api/v1/evolution/stats');
    return resp.json();
  },

  /** 触发进化扫描（HTTP） */
  evolutionScan: async () => {
    const resp = await clawbotFetch('/api/v1/evolution/scan', { method: 'POST' });
    return resp.json();
  },
};
