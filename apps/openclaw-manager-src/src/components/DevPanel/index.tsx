import { useState, useEffect, useRef, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { api, isTauri } from '@/lib/tauri';
import type {
  ClawbotBotMatrixEntry,
  ManagedServiceStatus,
  ManagedEndpointStatus,
  DiagnosticResult,
} from '@/lib/tauri';
import {
  Play, Square, RotateCw, FileText, Activity, Server,
  Terminal, RefreshCw, CheckCircle, XCircle, Loader2,
  Cpu, MemoryStick, HardDrive, Stethoscope, Zap, Wifi,
} from 'lucide-react';
import { createLogger } from '@/lib/logger';

const logger = createLogger('DevPanel');

/**
 * DevPanel — 开发者工作台（功能完整版）
 *
 * 三栏布局：
 * - 左侧：服务管理（启停控制）+ Bot 实时状态 + 端点健康 + 系统诊断
 * - 中间：实时日志查看器
 * - 右侧：系统资源仪表盘 + 服务健康概况
 */

/* ── 系统资源类型 ────────────────────── */
interface SystemResources {
  cpu_load_1m?: number;
  memory_percent?: number;
  disk_used_percent?: number;
}

/* ── toast 提示 ─────────────────────── */
function showToast(msg: string, type: 'success' | 'error' | 'info' = 'info') {
  // 使用全局 toast 系统（如果存在），否则回退到 console
  const event = new CustomEvent('toast', { detail: { message: msg, type } });
  window.dispatchEvent(event);
  if (type === 'error') logger.error(msg);
  else logger.info(msg);
}

export default function DevPanel() {
  /* ── 状态 ────────────────────────────── */
  const [bots, setBots] = useState<ClawbotBotMatrixEntry[]>([]);
  const [services, setServices] = useState<ManagedServiceStatus[]>([]);
  const [endpoints, setEndpoints] = useState<ManagedEndpointStatus[]>([]);
  const [diagnostics, setDiagnostics] = useState<DiagnosticResult[]>([]);
  const [resources, setResources] = useState<SystemResources | null>(null);
  const [logLines, setLogLines] = useState<string[]>(['等待日志加载...']);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [diagRunning, setDiagRunning] = useState(false);
  const [selectedLogService, setSelectedLogService] = useState<string>('gateway');

  const logContainerRef = useRef<HTMLDivElement>(null);
  const logPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── 自动滚动到日志底部 ──────────────── */
  const scrollToBottom = useCallback(() => {
    if (logContainerRef.current) {
      const el = logContainerRef.current;
      // 仅在用户已滚动到底部附近时自动滚动
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      if (isNearBottom) {
        el.scrollTop = el.scrollHeight;
      }
    }
  }, []);

  /* ── 加载 Bot 矩阵（真实数据） ────────── */
  const loadBots = useCallback(async () => {
    try {
      const data = await api.getClawbotBotMatrix();
      setBots(data);
    } catch (e) {
      logger.debug('Bot 矩阵加载失败', e);
    }
  }, []);

  /* ── 加载服务状态 ──────────────────────── */
  const loadServices = useCallback(async () => {
    try {
      const data = await api.getManagedServicesStatus();
      setServices(data);
    } catch (e) {
      logger.debug('服务状态加载失败', e);
    }
  }, []);

  /* ── 加载端点健康 ──────────────────────── */
  const loadEndpoints = useCallback(async () => {
    try {
      const data = await api.getManagedEndpointsStatus();
      setEndpoints(data);
    } catch (e) {
      logger.debug('端点健康加载失败', e);
    }
  }, []);

  /* ── 加载系统资源 ──────────────────────── */
  const loadResources = useCallback(async () => {
    try {
      const res = await invoke<SystemResources>('get_system_resources');
      setResources(res);
    } catch (e) {
      logger.debug('系统资源查询失败', e);
    }
  }, []);

  /* ── 加载日志 ──────────────────────────── */
  const loadLogs = useCallback(async () => {
    try {
      let lines: string[];
      if (selectedLogService === 'gateway') {
        lines = await api.getLogs(200);
      } else {
        lines = await api.getManagedServiceLogs(selectedLogService, 200);
      }
      if (lines && lines.length > 0) {
        setLogLines(lines);
        // 延迟一帧执行滚动，确保 DOM 已更新
        requestAnimationFrame(scrollToBottom);
      }
    } catch (e) {
      logger.debug('日志加载失败', e);
    }
  }, [selectedLogService, scrollToBottom]);

  /* ── 运行系统诊断 ──────────────────────── */
  const runDiagnostics = useCallback(async () => {
    setDiagRunning(true);
    try {
      const results = await api.runDoctor();
      setDiagnostics(results);
      const passed = results.filter(r => r.passed).length;
      showToast(`诊断完成: ${passed}/${results.length} 项通过`, passed === results.length ? 'success' : 'info');
    } catch (e) {
      showToast('诊断执行失败', 'error');
      logger.error('诊断失败', e);
    } finally {
      setDiagRunning(false);
    }
  }, []);

  /* ── 服务操作（启动/停止/重启） ──────── */
  const handleServiceAction = useCallback(async (action: 'start' | 'stop' | 'restart') => {
    const actionNames: Record<string, string> = { start: '启动', stop: '停止', restart: '重启' };
    setActionLoading(prev => ({ ...prev, [action]: true }));
    try {
      await api.controlAllManagedServices(action);
      showToast(`全部服务${actionNames[action]}指令已发送`, 'success');
      // 等 2 秒后刷新状态
      setTimeout(() => {
        loadServices();
        loadBots();
        loadEndpoints();
      }, 2000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      showToast(`${actionNames[action]}失败: ${msg}`, 'error');
    } finally {
      setActionLoading(prev => ({ ...prev, [action]: false }));
    }
  }, [loadServices, loadBots, loadEndpoints]);

  /* ── 初始化 + 轮询 ────────────────────── */
  useEffect(() => {
    if (!isTauri()) return;

    // 首次加载全部数据
    loadBots();
    loadServices();
    loadEndpoints();
    loadResources();
    loadLogs();

    // 每 15 秒刷新资源 + 服务状态
    const statusTimer = setInterval(() => {
      loadResources();
      loadServices();
      loadEndpoints();
    }, 15000);

    // 每 30 秒刷新 Bot 矩阵
    const botTimer = setInterval(loadBots, 30000);

    return () => {
      clearInterval(statusTimer);
      clearInterval(botTimer);
    };
  }, [loadBots, loadServices, loadEndpoints, loadResources, loadLogs]);

  /* ── 日志切换时重新加载 + 启动轮询 ────── */
  useEffect(() => {
    if (!isTauri()) return;
    loadLogs();

    // 每 5 秒刷新日志
    if (logPollRef.current) clearInterval(logPollRef.current);
    logPollRef.current = setInterval(loadLogs, 5000);

    return () => {
      if (logPollRef.current) clearInterval(logPollRef.current);
    };
  }, [loadLogs]);

  /* ── 日志源选项 ────────────────────────── */
  const logSources = [
    { id: 'gateway', label: 'Gateway' },
    ...services.map(s => ({ id: s.label, label: s.name })),
  ];

  /* ── 非 Tauri 环境提示 ─────────────────── */
  if (!isTauri()) {
    return (
      <div className="flex items-center justify-center h-full text-[#8B99A8]">
        <p>开发者工作台仅在桌面应用中可用</p>
      </div>
    );
  }

  /* ── 进度条组件 ────────────────────────── */
  const ProgressBar = ({ value, color }: { value: number; color: string }) => (
    <div className="w-full bg-[#1E2633] rounded-full h-1.5">
      <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${Math.min(value, 100)}%` }} />
    </div>
  );

  /* ── 统计数字 ──────────────────────────── */
  const runningServices = services.filter(s => s.running).length;
  const healthyEndpoints = endpoints.filter(e => e.healthy).length;
  const readyBots = bots.filter(b => b.ready).length;

  return (
    <div className="flex h-screen bg-[var(--bg-primary,#0D0F14)] text-[#F0F3F8]">
      {/* ═══ 左侧面板 ═══ */}
      <div className="w-64 bg-[var(--bg-secondary,#161B22)] border-r border-[#1E2633] p-4 flex flex-col gap-5 overflow-y-auto scroll-container">
        {/* 服务管理 */}
        <section>
          <h3 className="text-xs font-medium text-[#8B99A8] uppercase tracking-wider mb-3">
            服务管理
          </h3>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleServiceAction('start')}
              disabled={actionLoading.start}
              className="flex items-center gap-2 px-3 py-2 bg-[#00D4FF]/10 hover:bg-[#00D4FF]/20 rounded-lg text-[#00D4FF] transition-colors text-sm disabled:opacity-50"
            >
              {actionLoading.start ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              <span>启动全部</span>
            </button>
            <button
              onClick={() => handleServiceAction('stop')}
              disabled={actionLoading.stop}
              className="flex items-center gap-2 px-3 py-2 bg-[#FF4B4B]/10 hover:bg-[#FF4B4B]/20 rounded-lg text-[#FF4B4B] transition-colors text-sm disabled:opacity-50"
            >
              {actionLoading.stop ? <Loader2 className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
              <span>停止全部</span>
            </button>
            <button
              onClick={() => handleServiceAction('restart')}
              disabled={actionLoading.restart}
              className="flex items-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg transition-colors text-sm disabled:opacity-50"
            >
              {actionLoading.restart ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCw className="w-4 h-4" />}
              <span>重启全部</span>
            </button>
          </div>
        </section>

        {/* 服务状态 */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-medium text-[#8B99A8] uppercase tracking-wider">
              服务 ({runningServices}/{services.length})
            </h3>
            <button onClick={loadServices} className="text-[#8B99A8] hover:text-[#00D4FF] transition-colors" title="刷新">
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>
          <div className="flex flex-col gap-1.5">
            {services.length === 0 ? (
              <p className="text-xs text-[#8B99A8]">加载中...</p>
            ) : services.map(svc => (
              <div key={svc.label} className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-[#1E2633] transition-colors">
                <div className={`w-2 h-2 rounded-full shrink-0 ${svc.running ? 'bg-[#00C37D]' : 'bg-[#FF4B4B]'}`} />
                <span className="truncate flex-1">{svc.name}</span>
                <span className="text-[#8B99A8] shrink-0">{svc.running ? `PID ${svc.pid}` : '已停止'}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Bot 矩阵 */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-medium text-[#8B99A8] uppercase tracking-wider">
              Bot ({readyBots}/{bots.length})
            </h3>
            <button onClick={loadBots} className="text-[#8B99A8] hover:text-[#00D4FF] transition-colors" title="刷新">
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>
          <div className="flex flex-col gap-1.5">
            {bots.length === 0 ? (
              <p className="text-xs text-[#8B99A8]">加载中...</p>
            ) : bots.map(bot => (
              <div key={bot.id} className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-[#1E2633] transition-colors" title={`模型: ${bot.route_model}`}>
                <div className={`w-2 h-2 rounded-full shrink-0 ${bot.ready ? 'bg-[#00C37D]' : 'bg-[#FF4B4B]'}`} />
                <span className="truncate flex-1">{bot.name}</span>
                <span className="text-[#8B99A8] shrink-0 text-[10px]">{bot.route_provider}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 端点健康 */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-medium text-[#8B99A8] uppercase tracking-wider">
              端点 ({healthyEndpoints}/{endpoints.length})
            </h3>
            <button onClick={loadEndpoints} className="text-[#8B99A8] hover:text-[#00D4FF] transition-colors" title="刷新">
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>
          <div className="flex flex-col gap-1.5">
            {endpoints.length === 0 ? (
              <p className="text-xs text-[#8B99A8]">加载中...</p>
            ) : endpoints.map(ep => (
              <div key={ep.id} className="flex items-center gap-2 text-xs px-2 py-1.5 rounded hover:bg-[#1E2633] transition-colors" title={ep.error || ep.address}>
                {ep.healthy ? (
                  <Wifi className="w-3 h-3 text-[#00C37D] shrink-0" />
                ) : (
                  <XCircle className="w-3 h-3 text-[#FF4B4B] shrink-0" />
                )}
                <span className="truncate flex-1">{ep.name}</span>
                <span className="text-[#8B99A8] shrink-0 text-[10px]">{ep.address}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 系统诊断 */}
        <section>
          <button
            onClick={runDiagnostics}
            disabled={diagRunning}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg transition-colors text-sm disabled:opacity-50"
          >
            {diagRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Stethoscope className="w-4 h-4" />}
            <span>{diagRunning ? '诊断中...' : '运行系统诊断'}</span>
          </button>
          {diagnostics.length > 0 && (
            <div className="mt-2 flex flex-col gap-1">
              {diagnostics.map((d, i) => (
                <div key={i} className="flex items-start gap-2 text-xs px-2 py-1" title={d.suggestion || d.message}>
                  {d.passed ? (
                    <CheckCircle className="w-3 h-3 text-[#00C37D] shrink-0 mt-0.5" />
                  ) : (
                    <XCircle className="w-3 h-3 text-[#FF4B4B] shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1 min-w-0">
                    <span className="block truncate">{d.name}</span>
                    {!d.passed && d.suggestion && (
                      <span className="block text-[10px] text-[#FF4B4B]/80 truncate">{d.suggestion}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* ═══ 中间主区域 — 实时日志 ═══ */}
      <div className="flex-1 flex flex-col">
        {/* 日志标签栏 */}
        <div className="flex items-center gap-2 px-4 py-2 bg-[var(--bg-secondary,#161B22)] border-b border-[#1E2633]">
          <Terminal className="w-4 h-4 text-[#00D4FF]" />
          <span className="text-sm font-medium">实时日志</span>
          <div className="flex-1" />

          {/* 日志源选择 */}
          <select
            value={selectedLogService}
            onChange={e => setSelectedLogService(e.target.value)}
            className="bg-[#1E2633] border border-[#2A3649] rounded px-2 py-1 text-xs text-[#F0F3F8] focus:outline-none focus:border-[#00D4FF]"
          >
            {logSources.map(s => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </select>

          {/* 手动刷新 */}
          <button
            onClick={loadLogs}
            className="text-[#8B99A8] hover:text-[#00D4FF] transition-colors p-1"
            title="刷新日志"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* 日志输出 */}
        <div
          ref={logContainerRef}
          className="flex-1 bg-[var(--bg-primary,#0D0F14)] p-4 font-mono text-xs overflow-y-auto scroll-container"
        >
          {logLines.map((line, i) => (
            <div
              key={i}
              className={`whitespace-pre-wrap leading-relaxed ${
                line.includes('[ERROR]') || line.includes('ERROR') ? 'text-[#FF4B4B]' :
                line.includes('[WARN]') || line.includes('WARNING') ? 'text-[#FFB347]' :
                line.includes('[SUCCESS]') || line.includes('SUCCESS') ? 'text-[#00C37D]' :
                'text-[#8B99A8]'
              }`}
            >
              {line}
            </div>
          ))}
          <div className="inline-block w-2 h-4 bg-[#00D4FF] animate-pulse mt-1" />
        </div>
      </div>

      {/* ═══ 右侧面板 — 系统资源 + 概况 ═══ */}
      <div className="w-72 bg-[var(--bg-secondary,#161B22)] border-l border-[#1E2633] p-4 flex flex-col gap-5 overflow-y-auto scroll-container">
        {/* 系统资源 */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-medium text-[#8B99A8] uppercase tracking-wider">
              系统资源
            </h3>
            <button onClick={loadResources} className="text-[#8B99A8] hover:text-[#00D4FF] transition-colors" title="刷新">
              <RefreshCw className="w-3 h-3" />
            </button>
          </div>
          <div className="flex flex-col gap-4">
            {/* CPU */}
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <Cpu className="w-3.5 h-3.5 text-[#00D4FF]" />
                <span className="text-xs text-[#8B99A8]">CPU 负载</span>
                <span className="ml-auto text-sm font-semibold text-white">
                  {resources?.cpu_load_1m?.toFixed(1) ?? '-'}
                </span>
              </div>
              <ProgressBar value={resources?.cpu_load_1m ? resources.cpu_load_1m * 10 : 0} color="bg-[#00D4FF]" />
            </div>
            {/* 内存 */}
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <MemoryStick className="w-3.5 h-3.5 text-purple-400" />
                <span className="text-xs text-[#8B99A8]">内存</span>
                <span className="ml-auto text-sm font-semibold text-white">
                  {resources?.memory_percent?.toFixed(0) ?? '-'}%
                </span>
              </div>
              <ProgressBar value={resources?.memory_percent ?? 0} color="bg-purple-500" />
            </div>
            {/* 磁盘 */}
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <HardDrive className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs text-[#8B99A8]">磁盘</span>
                <span className="ml-auto text-sm font-semibold text-white">
                  {resources?.disk_used_percent?.toFixed(0) ?? '-'}%
                </span>
              </div>
              <ProgressBar value={resources?.disk_used_percent ?? 0} color="bg-amber-500" />
            </div>
          </div>
        </section>

        {/* 分隔线 */}
        <div className="border-t border-[#1E2633]" />

        {/* 健康概况 */}
        <section>
          <h3 className="text-xs font-medium text-[#8B99A8] uppercase tracking-wider mb-3">
            健康概况
          </h3>
          <div className="flex flex-col gap-3">
            {/* 服务 */}
            <div className="flex items-center gap-3 bg-[#1E2633] rounded-lg p-3">
              <Server className="w-5 h-5 text-[#00D4FF]" />
              <div className="flex-1">
                <p className="text-xs text-[#8B99A8]">管理服务</p>
                <p className="text-sm font-semibold text-white">
                  {runningServices}/{services.length} 运行中
                </p>
              </div>
              <div className={`w-3 h-3 rounded-full ${runningServices === services.length && services.length > 0 ? 'bg-[#00C37D]' : runningServices > 0 ? 'bg-[#FFB347]' : 'bg-[#FF4B4B]'}`} />
            </div>
            {/* Bot */}
            <div className="flex items-center gap-3 bg-[#1E2633] rounded-lg p-3">
              <Zap className="w-5 h-5 text-purple-400" />
              <div className="flex-1">
                <p className="text-xs text-[#8B99A8]">AI Bot</p>
                <p className="text-sm font-semibold text-white">
                  {readyBots}/{bots.length} 就绪
                </p>
              </div>
              <div className={`w-3 h-3 rounded-full ${readyBots === bots.length && bots.length > 0 ? 'bg-[#00C37D]' : readyBots > 0 ? 'bg-[#FFB347]' : 'bg-[#FF4B4B]'}`} />
            </div>
            {/* 端点 */}
            <div className="flex items-center gap-3 bg-[#1E2633] rounded-lg p-3">
              <Activity className="w-5 h-5 text-amber-400" />
              <div className="flex-1">
                <p className="text-xs text-[#8B99A8]">API 端点</p>
                <p className="text-sm font-semibold text-white">
                  {healthyEndpoints}/{endpoints.length} 健康
                </p>
              </div>
              <div className={`w-3 h-3 rounded-full ${healthyEndpoints === endpoints.length && endpoints.length > 0 ? 'bg-[#00C37D]' : healthyEndpoints > 0 ? 'bg-[#FFB347]' : 'bg-[#FF4B4B]'}`} />
            </div>
          </div>
        </section>

        {/* 分隔线 */}
        <div className="border-t border-[#1E2633]" />

        {/* 快捷操作 */}
        <section>
          <h3 className="text-xs font-medium text-[#8B99A8] uppercase tracking-wider mb-3">
            快捷操作
          </h3>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => loadLogs()}
              className="flex items-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg text-sm transition-colors"
            >
              <FileText className="w-4 h-4" />
              <span>刷新日志</span>
            </button>
            <button
              onClick={async () => {
                loadBots();
                loadServices();
                loadEndpoints();
                loadResources();
                showToast('已刷新全部数据', 'info');
              }}
              className="flex items-center gap-2 px-3 py-2 bg-[#1E2633] hover:bg-[#2A3649] rounded-lg text-sm transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              <span>全部刷新</span>
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
