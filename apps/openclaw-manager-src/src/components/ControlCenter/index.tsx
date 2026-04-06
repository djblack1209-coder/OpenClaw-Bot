import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  Loader2,
  Play,
  Power,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  ShieldCheck,
  Square,
} from 'lucide-react';
import clsx from 'clsx';
import {
  api,
  ClawbotBotMatrixEntry,
  ClawbotRuntimeConfig,
  isTauri,
  ManagedEndpointStatus,
  ManagedServiceAction,
  ManagedServiceStatus,
  OpenclawUsageSnapshot,
} from '../../lib/tauri';
import { toast } from 'sonner';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';

const ACTION_LABEL: Record<ManagedServiceAction, string> = {
  start: '启动',
  stop: '停止',
  restart: '重启',
};

/** 配置字段的中文标签、描述和占位符映射 */
const CONFIG_FIELD_META: Record<string, { label: string; hint?: string; placeholder?: string }> = {
  G4F_BASE_URL: {
    label: '🏷️ 免费模型代理地址 (G4F)',
    hint: '连接 G4F 免费模型的 API 地址',
    placeholder: '默认: http://localhost:1337/v1',
  },
  KIRO_BASE_URL: {
    label: '🏷️ Kiro 模型代理地址',
    hint: '连接 Kiro 模型网关的 API 地址',
    placeholder: '默认: http://localhost:8080/v1',
  },
  IBKR_HOST: {
    label: '🏷️ IBKR 券商交易地址',
    hint: 'IB Gateway / TWS 的连接地址',
    placeholder: '默认: 127.0.0.1',
  },
  IBKR_PORT: {
    label: '🏷️ IBKR 交易端口',
    hint: 'IB Gateway 模拟盘 4002 / 实盘 4001',
    placeholder: '默认: 4002',
  },
  IBKR_ACCOUNT: {
    label: '🏷️ IBKR 账户名',
    hint: 'Interactive Brokers 的账户 ID',
    placeholder: '例如: DU1234567',
  },
  IBKR_BUDGET: {
    label: '🏷️ IBKR 单日预算 (USD)',
    hint: '每日最大交易金额限制，防止超额下单',
    placeholder: '例如: 1000',
  },
  IBKR_AUTOSTART: {
    label: '🏷️ IBKR 自动启动',
    hint: '全部启动/重启时是否自动拉起 IB Gateway',
  },
  IBKR_START_CMD: {
    label: '🏷️ IBKR 启动命令',
    hint: '自定义启动 IB Gateway 的系统命令',
    placeholder: '默认: open -a "IB Gateway"',
  },
  IBKR_STOP_CMD: {
    label: '🏷️ IBKR 停止命令',
    hint: '自定义停止 IB Gateway 的系统命令',
    placeholder: '默认: pkill -f "IB Gateway" || pkill -f "Trader Workstation" || true',
  },
  NOTIFY_CHAT_ID: {
    label: '🏷️ 通知群/频道 ID',
    hint: 'Telegram 群组或频道的 Chat ID，用于接收系统通知',
    placeholder: '例如: -1001234567890',
  },
};

/** 根据配置键获取中文标签，找不到则回退为原始键名 */
const getFieldLabel = (key: string): string =>
  CONFIG_FIELD_META[key]?.label ?? key;

/** 根据配置键获取描述提示 */
const getFieldHint = (key: string): string | undefined =>
  CONFIG_FIELD_META[key]?.hint;

/** 根据配置键获取 placeholder */
const getFieldPlaceholder = (key: string): string | undefined =>
  CONFIG_FIELD_META[key]?.placeholder;

const DEFAULT_RUNTIME_CONFIG: ClawbotRuntimeConfig = {
  G4F_BASE_URL: '',
  KIRO_BASE_URL: '',
  IBKR_HOST: '',
  IBKR_PORT: '',
  IBKR_ACCOUNT: '',
  IBKR_BUDGET: '',
  IBKR_AUTOSTART: 'true',
  IBKR_START_CMD: '',
  IBKR_STOP_CMD: '',
  NOTIFY_CHAT_ID: '',
};

const CLAWBOT_PIPELINE_LABELS = [
  'ai.openclaw.g4f',
  'ai.openclaw.kiro-gateway',
  'ai.openclaw.clawbot-agent',
];

const DEFAULT_LOG_LABEL = 'ai.openclaw.clawbot-agent';

const getLogLineClass = (line: string) => {
  if (line.includes('ERROR') || line.includes('Error') || line.includes('error') || line.includes('Traceback')) {
    return 'text-red-400';
  }
  if (line.includes('WARN') || line.includes('Warn') || line.includes('warning')) {
    return 'text-amber-400';
  }
  return 'text-gray-400';
};

const USAGE_META_KEYS = new Set(['provider', 'name', 'id', 'accountId', 'account', 'source']);

const getUsageProviderName = (provider: Record<string, unknown>) => {
  const candidates = ['provider', 'name', 'id', 'accountId'];
  for (const key of candidates) {
    const value = provider[key];
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return 'unknown-provider';
};

const getUsageProviderDetails = (provider: Record<string, unknown>) =>
  Object.entries(provider)
    .filter(([key, value]) => !USAGE_META_KEYS.has(key) && (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'))
    .slice(0, 6)
    .map(([key, value]) => `${key}: ${String(value)}`);

export function ControlCenter() {
  const [services, setServices] = useState<ManagedServiceStatus[]>([]);
  const [endpoints, setEndpoints] = useState<ManagedEndpointStatus[]>([]);
  const [runtimeConfig, setRuntimeConfig] = useState<ClawbotRuntimeConfig>(DEFAULT_RUNTIME_CONFIG);
  const [botMatrix, setBotMatrix] = useState<ClawbotBotMatrixEntry[]>([]);
  const [usageSnapshot, setUsageSnapshot] = useState<OpenclawUsageSnapshot>({ providers: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [allActionLoading, setAllActionLoading] = useState<ManagedServiceAction | null>(null);
  const [serviceActionLoading, setServiceActionLoading] = useState<Record<string, ManagedServiceAction | null>>({});
  const [savingConfig, setSavingConfig] = useState(false);
  const [savingAndRestarting, setSavingAndRestarting] = useState(false);
  const [selectedLogLabel, setSelectedLogLabel] = useState<string>(DEFAULT_LOG_LABEL);
  const [serviceLogs, setServiceLogs] = useState<string[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [autoRefreshLogs, setAutoRefreshLogs] = useState(true);
  const [showStopAllConfirm, setShowStopAllConfirm] = useState(false);
  const [stopServiceTarget, setStopServiceTarget] = useState<string | null>(null);

  const runningCount = useMemo(
    () => services.filter((service) => service.running).length,
    [services]
  );

  const healthyEndpointsCount = useMemo(
    () => endpoints.filter((endpoint) => endpoint.healthy).length,
    [endpoints]
  );

  const readyBotCount = useMemo(
    () => botMatrix.filter((bot) => bot.ready).length,
    [botMatrix]
  );

  const usageProviderCount = useMemo(
    () => usageSnapshot.providers.length,
    [usageSnapshot]
  );

  // 日志容器引用，用于自动滚动到底部
  const logContainerRef = useRef<HTMLDivElement>(null);

  const fetchAll = useCallback(async (silent = false) => {
    if (!isTauri()) {
      setLoading(false);
      return;
    }

    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      // 核心状态：必须成功才能渲染
      const [serviceStatus, configValues, endpointStatus, matrix] = await Promise.all([
        api.getManagedServicesStatus(),
        api.getClawbotRuntimeConfig(),
        api.getManagedEndpointsStatus(),
        api.getClawbotBotMatrix(),
      ]);
      setServices(serviceStatus);
      setRuntimeConfig({ ...DEFAULT_RUNTIME_CONFIG, ...configValues });
      setEndpoints(endpointStatus);
      setBotMatrix(matrix);
      if (!serviceStatus.some((service) => service.label === selectedLogLabel)) {
        const fallback = serviceStatus.find((service) => service.label === DEFAULT_LOG_LABEL)?.label;
        setSelectedLogLabel(fallback || serviceStatus[0]?.label || DEFAULT_LOG_LABEL);
      }

      // 非关键数据：失败不阻塞 UI
      api.getOpenclawUsageSnapshot()
        .then((usage) => {
          setUsageSnapshot({ providers: usage.providers || [], updatedAt: usage.updatedAt });
        })
        .catch(() => {
          setUsageSnapshot({ providers: [] });
        });
    } catch (error) {
      toast.error(`刷新失败: ${String(error)}`);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLogLabel]);

  const fetchLogs = useCallback(async (label: string) => {
    if (!label || !isTauri()) {
      setServiceLogs([]);
      return;
    }

    setLogsLoading(true);
    try {
      const logs = await api.getManagedServiceLogs(label, 180);
      setServiceLogs(logs);
    } catch (error) {
      setServiceLogs([`读取日志失败: ${String(error)}`]);
    } finally {
      setLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    // 每 10 秒自动刷新服务矩阵状态
    const refreshTimer = setInterval(() => {
      fetchAll(true);
    }, 10000);
    return () => clearInterval(refreshTimer);
  }, [fetchAll]);

  useEffect(() => {
    fetchLogs(selectedLogLabel);
  }, [selectedLogLabel, fetchLogs]);

  useEffect(() => {
    if (!autoRefreshLogs || !selectedLogLabel) {
      return;
    }
    const timer = setInterval(() => {
      fetchLogs(selectedLogLabel);
    }, 3000);
    return () => clearInterval(timer);
  }, [autoRefreshLogs, selectedLogLabel, fetchLogs]);

  // 日志更新时自动滚动到底部
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [serviceLogs]);

  const handleAllAction = async (action: ManagedServiceAction) => {
    setAllActionLoading(action);
    try {
      const result = await api.controlAllManagedServices(action);
      toast.success(result || `全部服务已${ACTION_LABEL[action]}`);
      await fetchAll(true);
      await fetchLogs(selectedLogLabel);
    } catch (error) {
      toast.error(`总控操作失败: ${String(error)}`);
    } finally {
      setAllActionLoading(null);
    }
  };

  const handleServiceAction = async (label: string, action: ManagedServiceAction) => {
    setServiceActionLoading((prev) => ({ ...prev, [label]: action }));
    try {
      const result = await api.controlManagedService(label, action);
      toast.success(result);
      await fetchAll(true);
      await fetchLogs(selectedLogLabel);
    } catch (error) {
      toast.error(`服务操作失败: ${String(error)}`);
    } finally {
      setServiceActionLoading((prev) => ({ ...prev, [label]: null }));
    }
  };

  const updateConfigValue = (key: keyof ClawbotRuntimeConfig, value: string) => {
    setRuntimeConfig((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveConfig = async () => {
    // 验证数值字段（端口号和预算金额）
    if (runtimeConfig.IBKR_PORT.trim()) {
      const port = Number(runtimeConfig.IBKR_PORT);
      if (isNaN(port) || port < 0 || !Number.isInteger(port)) {
        toast.error('IBKR 端口号必须是非负整数');
        return;
      }
    }
    if (runtimeConfig.IBKR_BUDGET.trim()) {
      const budget = Number(runtimeConfig.IBKR_BUDGET);
      if (isNaN(budget) || budget < 0) {
        toast.error('IBKR 预算金额不能为负数');
        return;
      }
    }

    setSavingConfig(true);
    try {
      const result = await api.saveClawbotRuntimeConfig(runtimeConfig);
      toast.success(result);
      await fetchAll(true);
    } catch (error) {
      toast.error(`保存配置失败: ${String(error)}`);
    } finally {
      setSavingConfig(false);
    }
  };

  const handleSaveAndRestart = async () => {
    // 验证数值字段（端口号和预算金额）
    if (runtimeConfig.IBKR_PORT.trim()) {
      const port = Number(runtimeConfig.IBKR_PORT);
      if (isNaN(port) || port < 0 || !Number.isInteger(port)) {
        toast.error('IBKR 端口号必须是非负整数');
        return;
      }
    }
    if (runtimeConfig.IBKR_BUDGET.trim()) {
      const budget = Number(runtimeConfig.IBKR_BUDGET);
      if (isNaN(budget) || budget < 0) {
        toast.error('IBKR 预算金额不能为负数');
        return;
      }
    }

    setSavingAndRestarting(true);
    try {
      await api.saveClawbotRuntimeConfig(runtimeConfig);
      for (const label of CLAWBOT_PIPELINE_LABELS) {
        await api.controlManagedService(label, 'restart');
      }
      toast.success('ClawBot 链路配置已保存并重启（g4f / Kiro / Agent）');
      await fetchAll(true);
      await fetchLogs(selectedLogLabel);
    } catch (error) {
      toast.error(`保存并重启失败: ${String(error)}`);
    } finally {
      setSavingAndRestarting(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-claw-500" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-6"
      >
        <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-claw-400 mb-2">
                <ShieldCheck size={18} />
                <span className="text-sm font-medium">最高权限总控中心</span>
              </div>
              <h2 className="text-xl font-semibold text-white">OpenClaw + ClawBot 总开关</h2>
              <p className="text-sm text-gray-400 mt-1">
                当前运行 {runningCount}/{services.length} 个核心服务
              </p>
              <p className="text-sm text-gray-500 mt-0.5">
                链路连通 {healthyEndpointsCount}/{endpoints.length}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => fetchAll(true)}
                disabled={refreshing || allActionLoading !== null}
                className="btn-secondary flex items-center gap-2"
              >
                {refreshing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                刷新状态
              </button>
              <button
                onClick={() => handleAllAction('start')}
                disabled={allActionLoading !== null}
                className="btn-secondary flex items-center gap-2"
              >
                {allActionLoading === 'start' ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                全部启动
              </button>
              <button
                onClick={() => setShowStopAllConfirm(true)}
                disabled={allActionLoading !== null}
                className="btn-secondary flex items-center gap-2"
              >
                {allActionLoading === 'stop' ? <Loader2 size={16} className="animate-spin" /> : <Square size={16} />}
                全部停止
              </button>
              <button
                onClick={() => handleAllAction('restart')}
                disabled={allActionLoading !== null}
                className="btn-primary flex items-center gap-2"
              >
                {allActionLoading === 'restart' ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <RotateCcw size={16} />
                )}
                全部重启
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
            <div className="flex items-center gap-2 mb-4">
              <Activity size={18} className="text-accent-cyan" />
              <h3 className="text-lg font-semibold text-white">服务矩阵</h3>
            </div>

            <div className="space-y-3">
              {services.length === 0 ? (
                <div className="flex items-center justify-center py-8 text-gray-500 text-sm bg-dark-800 rounded-xl border border-dark-600 border-dashed">
                  暂无已注册服务
                </div>
              ) : services.map((service) => {
                const actionLoading = serviceActionLoading[service.label];
                return (
                  <div
                    key={service.label}
                    className="bg-dark-800 rounded-xl border border-dark-600 p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-medium text-white">{service.name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">{service.label}</p>
                        <p className="text-xs text-gray-500 mt-1">
                          {service.running ? `运行中 · PID ${service.pid ?? '-'}` : '未运行'}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span
                          className={clsx(
                            'px-2 py-1 rounded-md text-xs border',
                            service.running
                              ? 'bg-green-500/10 text-green-300 border-green-500/30'
                              : 'bg-red-500/10 text-red-300 border-red-500/30'
                          )}
                        >
                          {service.running ? '运行中' : '已停止'}
                        </span>
                        <button
                          onClick={() => handleServiceAction(service.label, 'start')}
                          disabled={!!actionLoading}
                          className="btn-secondary px-3 py-2 text-sm"
                        >
                          {actionLoading === 'start' ? <Loader2 size={14} className="animate-spin" /> : '启动'}
                        </button>
                        <button
                          onClick={() => setStopServiceTarget(service.label)}
                          disabled={!!actionLoading}
                          className="btn-secondary px-3 py-2 text-sm"
                        >
                          {actionLoading === 'stop' ? <Loader2 size={14} className="animate-spin" /> : '停止'}
                        </button>
                        <button
                          onClick={() => handleServiceAction(service.label, 'restart')}
                          disabled={!!actionLoading}
                          className="btn-primary px-3 py-2 text-sm"
                        >
                          {actionLoading === 'restart' ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            '重启'
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-5 pt-5 border-t border-dark-600">
              <div className="flex items-center gap-2 mb-3">
                <Activity size={16} className="text-accent-green" />
                <p className="text-sm font-medium text-gray-300">链路连通性</p>
              </div>
              <div className="space-y-2">
                {endpoints.length === 0 ? (
                  <div className="flex items-center justify-center py-6 text-gray-500 text-sm bg-dark-800 rounded-lg border border-dark-600 border-dashed">
                    暂无链路端点
                  </div>
                ) : endpoints.map((endpoint) => (
                  <div
                    key={endpoint.id}
                    className="bg-dark-800 rounded-lg border border-dark-600 px-3 py-2 flex items-center justify-between gap-3"
                  >
                    <div>
                      <p className="text-sm text-gray-200">{endpoint.name}</p>
                      <p className="text-xs text-gray-500">{endpoint.address}</p>
                    </div>
                    <span
                      className={clsx(
                        'px-2 py-1 rounded-md text-xs border',
                        endpoint.healthy
                          ? 'bg-green-500/10 text-green-300 border-green-500/30'
                          : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                      )}
                    >
                      {endpoint.healthy ? '可达' : '不可达'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
            <div className="flex items-center gap-2 mb-4">
              <Settings2 size={18} className="text-accent-amber" />
              <h3 className="text-lg font-semibold text-white">ClawBot 运行配置</h3>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('G4F_BASE_URL')}</label>
                {getFieldHint('G4F_BASE_URL') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('G4F_BASE_URL')}</p>}
                <input
                  value={runtimeConfig.G4F_BASE_URL}
                  onChange={(e) => updateConfigValue('G4F_BASE_URL', e.target.value)}
                  className="input-base"
                  placeholder={getFieldPlaceholder('G4F_BASE_URL')}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('KIRO_BASE_URL')}</label>
                {getFieldHint('KIRO_BASE_URL') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('KIRO_BASE_URL')}</p>}
                <input
                  value={runtimeConfig.KIRO_BASE_URL}
                  onChange={(e) => updateConfigValue('KIRO_BASE_URL', e.target.value)}
                  className="input-base"
                  placeholder={getFieldPlaceholder('KIRO_BASE_URL')}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('IBKR_HOST')}</label>
                  {getFieldHint('IBKR_HOST') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('IBKR_HOST')}</p>}
                  <input
                    value={runtimeConfig.IBKR_HOST}
                    onChange={(e) => updateConfigValue('IBKR_HOST', e.target.value)}
                    className="input-base"
                    placeholder={getFieldPlaceholder('IBKR_HOST')}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('IBKR_PORT')}</label>
                  {getFieldHint('IBKR_PORT') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('IBKR_PORT')}</p>}
                  <input
                    value={runtimeConfig.IBKR_PORT}
                    onChange={(e) => updateConfigValue('IBKR_PORT', e.target.value)}
                    className="input-base"
                    placeholder={getFieldPlaceholder('IBKR_PORT')}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('IBKR_ACCOUNT')}</label>
                  {getFieldHint('IBKR_ACCOUNT') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('IBKR_ACCOUNT')}</p>}
                  <input
                    value={runtimeConfig.IBKR_ACCOUNT}
                    onChange={(e) => updateConfigValue('IBKR_ACCOUNT', e.target.value)}
                    className="input-base"
                    placeholder={getFieldPlaceholder('IBKR_ACCOUNT')}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('IBKR_BUDGET')}</label>
                  {getFieldHint('IBKR_BUDGET') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('IBKR_BUDGET')}</p>}
                  <input
                    value={runtimeConfig.IBKR_BUDGET}
                    onChange={(e) => updateConfigValue('IBKR_BUDGET', e.target.value)}
                    className="input-base"
                    placeholder={getFieldPlaceholder('IBKR_BUDGET')}
                  />
                </div>
              </div>
              <div className="bg-dark-800 rounded-xl border border-dark-600 p-3 space-y-3">
                <label className="flex items-center gap-2 text-sm text-gray-300">
                  <input
                    type="checkbox"
                    checked={(runtimeConfig.IBKR_AUTOSTART || 'true').toLowerCase() === 'true'}
                    onChange={(e) => updateConfigValue('IBKR_AUTOSTART', e.target.checked ? 'true' : 'false')}
                    className="w-4 h-4 rounded"
                  />
                  全部启动/重启时自动拉起 IBKR
                </label>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('IBKR_START_CMD')}</label>
                  {getFieldHint('IBKR_START_CMD') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('IBKR_START_CMD')}</p>}
                  <input
                    value={runtimeConfig.IBKR_START_CMD}
                    onChange={(e) => updateConfigValue('IBKR_START_CMD', e.target.value)}
                    className="input-base"
                    placeholder={getFieldPlaceholder('IBKR_START_CMD')}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('IBKR_STOP_CMD')}</label>
                  {getFieldHint('IBKR_STOP_CMD') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('IBKR_STOP_CMD')}</p>}
                  <input
                    value={runtimeConfig.IBKR_STOP_CMD}
                    onChange={(e) => updateConfigValue('IBKR_STOP_CMD', e.target.value)}
                    className="input-base"
                    placeholder={getFieldPlaceholder('IBKR_STOP_CMD')}
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-300 mb-1">{getFieldLabel('NOTIFY_CHAT_ID')}</label>
                {getFieldHint('NOTIFY_CHAT_ID') && <p className="text-xs text-gray-500 mb-2">{getFieldHint('NOTIFY_CHAT_ID')}</p>}
                <input
                  value={runtimeConfig.NOTIFY_CHAT_ID}
                  onChange={(e) => updateConfigValue('NOTIFY_CHAT_ID', e.target.value)}
                  className="input-base"
                  placeholder={getFieldPlaceholder('NOTIFY_CHAT_ID')}
                />
              </div>

              <div className="pt-2 flex flex-wrap gap-2">
                <button
                  onClick={handleSaveConfig}
                  disabled={savingConfig || savingAndRestarting}
                  className="btn-secondary flex items-center gap-2"
                >
                  {savingConfig ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                  保存配置
                </button>
                <button
                  onClick={handleSaveAndRestart}
                  disabled={savingConfig || savingAndRestarting}
                  className="btn-primary flex items-center gap-2"
                >
                  {savingAndRestarting ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Power size={16} />
                  )}
                  保存并重启 ClawBot 链路
                </button>
              </div>

              <div className="mt-5 pt-5 border-t border-dark-600">
                <div className="flex items-center justify-between gap-2 mb-3">
                  <p className="text-sm font-medium text-gray-300">多 Bot 矩阵</p>
                  <span className="text-xs text-gray-500">就绪 {readyBotCount}/{botMatrix.length}</span>
                </div>

                <div className="space-y-2">
                  {botMatrix.length === 0 ? (
                    <div className="flex items-center justify-center py-6 text-gray-500 text-sm bg-dark-800 rounded-lg border border-dark-600 border-dashed">
                      暂无 Bot 配置
                    </div>
                  ) : botMatrix.map((bot) => (
                    <div
                      key={bot.id}
                      className="bg-dark-800 rounded-lg border border-dark-600 px-3 py-2"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm text-gray-200">{bot.name}</p>
                          <p className="text-xs text-gray-500 mt-0.5">
                            @{bot.username || '-'} · {bot.route_provider}/{bot.route_model}
                          </p>
                          <p className="text-xs text-gray-500 mt-0.5 truncate">{bot.route_base_url || '未配置路由地址'}</p>
                        </div>
                        <div className="text-right">
                          <span
                            className={clsx(
                              'px-2 py-1 rounded-md text-xs border',
                              bot.ready
                                ? 'bg-green-500/10 text-green-300 border-green-500/30'
                                : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                            )}
                          >
                            {bot.ready ? '就绪' : '等待中'}
                          </span>
                          <p className="text-[11px] text-gray-500 mt-1">Token: {bot.token_masked || '未配置'}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-5 pt-5 border-t border-dark-600">
                <div className="flex items-center justify-between gap-2 mb-3">
                  <p className="text-sm font-medium text-gray-300">成本与配额快照</p>
                  <span className="text-xs text-gray-500">服务商 {usageProviderCount}</span>
                </div>

                {usageProviderCount === 0 ? (
                  <div className="bg-dark-800 rounded-lg border border-dark-600 px-3 py-3 text-xs text-gray-500">
                    当前没有可用的 provider usage 数据（需对应 provider 支持 usage endpoint 且凭据可读）。
                  </div>
                ) : (
                  <div className="space-y-2">
                    {usageSnapshot.providers.map((provider, index) => {
                      const name = getUsageProviderName(provider);
                      const details = getUsageProviderDetails(provider);
                      return (
                        <div
                          key={`${name}-${index}`}
                          className="bg-dark-800 rounded-lg border border-dark-600 px-3 py-2"
                        >
                          <p className="text-sm text-gray-200">{name}</p>
                          <div className="mt-1 text-xs text-gray-500 space-y-0.5">
                            {details.length === 0 ? (
                              <p>暂无可展示指标</p>
                            ) : (
                              details.map((line) => <p key={line}>{line}</p>)
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <p className="text-[11px] text-gray-500 mt-2">
                  更新时间：{usageSnapshot.updatedAt ? new Date(usageSnapshot.updatedAt).toLocaleString('zh-CN', { hour12: false }) : '未知'}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div>
              <h3 className="text-lg font-semibold text-white">统一日志观察窗</h3>
              <p className="text-xs text-gray-500 mt-0.5">可直接查看 OpenClaw / ClawBot 各核心服务日志</p>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative">
                <select
                  value={selectedLogLabel}
                  onChange={(e) => setSelectedLogLabel(e.target.value)}
                  className="appearance-none bg-dark-800 border border-dark-600 rounded-lg px-3 py-2 pr-8 text-sm text-gray-200"
                  aria-label="选择日志服务"
                >
                  {services.map((service) => (
                    <option key={service.label} value={service.label}>
                      {service.name}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500" />
              </div>

              <label className="flex items-center gap-2 text-xs text-gray-400">
                <input
                  type="checkbox"
                  checked={autoRefreshLogs}
                  onChange={(e) => setAutoRefreshLogs(e.target.checked)}
                  className="w-3 h-3 rounded"
                />
                自动刷新
              </label>

              <button
                onClick={() => fetchLogs(selectedLogLabel)}
                disabled={logsLoading}
                className="btn-secondary px-3 py-2 text-sm flex items-center gap-2"
              >
                {logsLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                刷新日志
              </button>
            </div>
          </div>

          <div ref={logContainerRef} className="h-72 overflow-y-auto rounded-xl bg-dark-800 border border-dark-600 p-3 font-mono text-xs">
            {logsLoading && serviceLogs.length === 0 ? (
              <div className="h-full flex items-center justify-center text-gray-500">
                <Loader2 className="w-5 h-5 animate-spin" />
              </div>
            ) : serviceLogs.length === 0 ? (
              <div className="h-full flex items-center justify-center text-gray-500">暂无日志输出</div>
            ) : (
              <div className="space-y-1">
                {serviceLogs.map((line, index) => (
                  <div key={`${index}-${line.slice(0, 24)}`} className={clsx('whitespace-pre-wrap break-all', getLogLineClass(line))}>
                    {line}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="bg-dark-700 rounded-2xl border border-dark-500 p-4 flex items-start gap-3">
          <AlertTriangle size={18} className="text-amber-400 mt-0.5" />
          <div>
            <p className="text-sm text-amber-300 font-medium">执行提示</p>
            <p className="text-xs text-gray-400 mt-1">
              这里是最高权限总控面板：可直接管理 LaunchAgent 服务与 ClawBot 关键运行参数。修改配置后建议使用“保存并重启 ClawBot 链路”。
            </p>
          </div>
        </div>
      </motion.div>

      {/* 全部停止确认对话框 */}
      <ConfirmDialog
        open={showStopAllConfirm}
        onClose={() => setShowStopAllConfirm(false)}
        onConfirm={() => {
          setShowStopAllConfirm(false);
          handleAllAction('stop');
        }}
        title="全部停止"
        description="确定要停止所有服务吗？停止后所有 Bot 和后台功能将暂停运行。"
        confirmText="全部停止"
        destructive
      />

      {/* 单个服务停止确认对话框 */}
      <ConfirmDialog
        open={stopServiceTarget !== null}
        onClose={() => setStopServiceTarget(null)}
        onConfirm={() => {
          if (stopServiceTarget) {
            handleServiceAction(stopServiceTarget, 'stop');
          }
          setStopServiceTarget(null);
        }}
        title="停止服务"
        description={`确定要停止「${services.find(s => s.label === stopServiceTarget)?.name ?? stopServiceTarget}」服务吗？`}
        confirmText="停止"
        destructive
      />
    </div>
  );
}
