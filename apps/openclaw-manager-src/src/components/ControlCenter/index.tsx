/**
 * ControlCenter — 最高权限总控中心
 *
 * 纯组合层：使用 useControlCenter hook 管理状态，
 * 子组件负责渲染各面板。
 */
import { motion } from 'framer-motion';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { useControlCenter } from './useControlCenter';
import { ControlHeader } from './ControlHeader';
import { ServiceMatrix } from './ServiceMatrix';
import { ConfigEditor } from './ConfigEditor';
import { BotMatrix } from './BotMatrix';
import { UsagePanel } from './UsagePanel';
import { LogViewer } from './LogViewer';

export function ControlCenter() {
  const cc = useControlCenter();

  if (cc.loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-claw-500" />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
        {/* 总控头部 */}
        <ControlHeader
          runningCount={cc.runningCount}
          totalServices={cc.services.length}
          healthyEndpointsCount={cc.healthyEndpointsCount}
          totalEndpoints={cc.endpoints.length}
          refreshing={cc.refreshing}
          allActionLoading={cc.allActionLoading}
          onRefresh={() => cc.fetchAll(true)}
          onStartAll={() => cc.handleAllAction('start')}
          onStopAll={() => cc.setShowStopAllConfirm(true)}
          onRestartAll={() => cc.handleAllAction('restart')}
        />

        {/* 左右两栏：服务矩阵 + 配置/Bot/用量 */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <ServiceMatrix
            services={cc.services}
            endpoints={cc.endpoints}
            serviceActionLoading={cc.serviceActionLoading}
            onServiceAction={cc.handleServiceAction}
            onStopService={cc.setStopServiceTarget}
          />

          <div className="space-y-0">
            <ConfigEditor
              runtimeConfig={cc.runtimeConfig}
              onUpdateConfig={(key, value) => cc.setRuntimeConfig((prev) => ({ ...prev, [key]: value }))}
              onSave={cc.handleSaveConfig}
              onSaveAndRestart={cc.handleSaveAndRestart}
              savingConfig={cc.savingConfig}
              savingAndRestarting={cc.savingAndRestarting}
            />
            <div className="bg-dark-700 rounded-b-2xl border border-t-0 border-dark-500 px-6 pb-6">
              <BotMatrix botMatrix={cc.botMatrix} readyBotCount={cc.readyBotCount} />
              <UsagePanel usageSnapshot={cc.usageSnapshot} usageProviderCount={cc.usageProviderCount} />
            </div>
          </div>
        </div>

        {/* 日志观察窗 */}
        <LogViewer
          services={cc.services}
          selectedLogLabel={cc.selectedLogLabel}
          onSelectLogLabel={cc.setSelectedLogLabel}
          serviceLogs={cc.serviceLogs}
          logsLoading={cc.logsLoading}
          autoRefreshLogs={cc.autoRefreshLogs}
          onToggleAutoRefresh={cc.setAutoRefreshLogs}
          onRefreshLogs={() => cc.fetchLogs(cc.selectedLogLabel)}
          logContainerRef={cc.logContainerRef}
        />

        {/* 执行提示 */}
        <div className="bg-dark-700 rounded-2xl border border-dark-500 p-4 flex items-start gap-3">
          <AlertTriangle size={18} className="text-amber-400 mt-0.5" />
          <div>
            <p className="text-sm text-amber-300 font-medium">执行提示</p>
            <p className="text-xs text-gray-400 mt-1">
              这里是最高权限总控面板：可直接管理 LaunchAgent 服务与 ClawBot 关键运行参数。修改配置后建议使用"保存并重启 ClawBot 链路"。
            </p>
          </div>
        </div>
      </motion.div>

      {/* 全部停止确认对话框 */}
      <ConfirmDialog
        open={cc.showStopAllConfirm}
        onClose={() => cc.setShowStopAllConfirm(false)}
        onConfirm={() => { cc.setShowStopAllConfirm(false); cc.handleAllAction('stop'); }}
        title="全部停止"
        description="确定要停止所有服务吗？停止后所有 Bot 和后台功能将暂停运行。"
        confirmText="全部停止"
        destructive
      />

      {/* 单个服务停止确认对话框 */}
      <ConfirmDialog
        open={cc.stopServiceTarget !== null}
        onClose={() => cc.setStopServiceTarget(null)}
        onConfirm={() => {
          if (cc.stopServiceTarget) cc.handleServiceAction(cc.stopServiceTarget, 'stop');
          cc.setStopServiceTarget(null);
        }}
        title="停止服务"
        description={`确定要停止「${cc.services.find((s) => s.label === cc.stopServiceTarget)?.name ?? cc.stopServiceTarget}」服务吗？`}
        confirmText="停止"
        destructive
      />
    </div>
  );
}
