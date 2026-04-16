/**
 * ControlCenter 核心业务逻辑 Hook
 *
 * 管理所有状态、数据拉取、操作回调，
 * 让 index.tsx 只负责组合渲染。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import {
  ACTION_LABEL,
  CLAWBOT_PIPELINE_LABELS,
  DEFAULT_LOG_LABEL,
  DEFAULT_RUNTIME_CONFIG,
} from './constants';

export function useControlCenter() {
  // ─── 状态 ──────────────────────────────────────────────
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

  // ─── 派生计算 ──────────────────────────────────────────
  const runningCount = useMemo(() => services.filter((s) => s.running).length, [services]);
  const healthyEndpointsCount = useMemo(() => endpoints.filter((e) => e.healthy).length, [endpoints]);
  const readyBotCount = useMemo(() => botMatrix.filter((b) => b.ready).length, [botMatrix]);
  const usageProviderCount = useMemo(() => usageSnapshot.providers.length, [usageSnapshot]);

  const logContainerRef = useRef<HTMLDivElement>(null);

  // ─── 数据拉取 ──────────────────────────────────────────
  const fetchAll = useCallback(async (silent = false) => {
    if (!isTauri()) { setLoading(false); return; }
    silent ? setRefreshing(true) : setLoading(true);

    try {
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

      if (!serviceStatus.some((s) => s.label === selectedLogLabel)) {
        const fallback = serviceStatus.find((s) => s.label === DEFAULT_LOG_LABEL)?.label;
        setSelectedLogLabel(fallback || serviceStatus[0]?.label || DEFAULT_LOG_LABEL);
      }

      // 非关键数据：失败不阻塞 UI
      api.getOpenclawUsageSnapshot()
        .then((usage) => setUsageSnapshot({ providers: usage.providers || [], updatedAt: usage.updatedAt }))
        .catch(() => setUsageSnapshot({ providers: [] }));
    } catch (error) {
      toast.error(`刷新失败: ${String(error)}`);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLogLabel]);

  const fetchLogs = useCallback(async (label: string) => {
    if (!label || !isTauri()) { setServiceLogs([]); return; }
    setLogsLoading(true);
    try {
      setServiceLogs(await api.getManagedServiceLogs(label, 180));
    } catch (error) {
      setServiceLogs([`读取日志失败: ${String(error)}`]);
    } finally {
      setLogsLoading(false);
    }
  }, []);

  // ─── 副作用：定时轮询 ──────────────────────────────────
  useEffect(() => {
    fetchAll();
    const timer = setInterval(() => fetchAll(true), 10000);
    return () => clearInterval(timer);
  }, [fetchAll]);

  useEffect(() => { fetchLogs(selectedLogLabel); }, [selectedLogLabel, fetchLogs]);

  useEffect(() => {
    if (!autoRefreshLogs || !selectedLogLabel) return;
    const timer = setInterval(() => fetchLogs(selectedLogLabel), 3000);
    return () => clearInterval(timer);
  }, [autoRefreshLogs, selectedLogLabel, fetchLogs]);

  // 日志更新时自动滚动到底部
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [serviceLogs]);

  // ─── 操作回调 ──────────────────────────────────────────
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
      toast.success(await api.controlManagedService(label, action));
      await fetchAll(true);
      await fetchLogs(selectedLogLabel);
    } catch (error) {
      toast.error(`服务操作失败: ${String(error)}`);
    } finally {
      setServiceActionLoading((prev) => ({ ...prev, [label]: null }));
    }
  };

  /** 校验数值字段（端口号/预算金额） */
  const validateNumericFields = (): boolean => {
    if (runtimeConfig.IBKR_PORT.trim()) {
      const port = Number(runtimeConfig.IBKR_PORT);
      if (isNaN(port) || port < 0 || !Number.isInteger(port)) {
        toast.error('IBKR 端口号必须是非负整数');
        return false;
      }
    }
    if (runtimeConfig.IBKR_BUDGET.trim()) {
      const budget = Number(runtimeConfig.IBKR_BUDGET);
      if (isNaN(budget) || budget < 0) {
        toast.error('IBKR 预算金额不能为负数');
        return false;
      }
    }
    return true;
  };

  const handleSaveConfig = async () => {
    if (!validateNumericFields()) return;
    setSavingConfig(true);
    try {
      toast.success(await api.saveClawbotRuntimeConfig(runtimeConfig));
      await fetchAll(true);
    } catch (error) {
      toast.error(`保存配置失败: ${String(error)}`);
    } finally {
      setSavingConfig(false);
    }
  };

  const handleSaveAndRestart = async () => {
    if (!validateNumericFields()) return;
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

  return {
    // 状态
    services,
    endpoints,
    runtimeConfig,
    setRuntimeConfig,
    botMatrix,
    usageSnapshot,
    loading,
    refreshing,
    allActionLoading,
    serviceActionLoading,
    savingConfig,
    savingAndRestarting,
    selectedLogLabel,
    setSelectedLogLabel,
    serviceLogs,
    logsLoading,
    autoRefreshLogs,
    setAutoRefreshLogs,
    showStopAllConfirm,
    setShowStopAllConfirm,
    stopServiceTarget,
    setStopServiceTarget,
    // 派生
    runningCount,
    healthyEndpointsCount,
    readyBotCount,
    usageProviderCount,
    logContainerRef,
    // 操作
    fetchAll,
    fetchLogs,
    handleAllAction,
    handleServiceAction,
    handleSaveConfig,
    handleSaveAndRestart,
  };
}
