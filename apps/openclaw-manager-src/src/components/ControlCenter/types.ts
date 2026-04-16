/**
 * ControlCenter 子组件共享类型定义
 */
import type {
  ClawbotBotMatrixEntry,
  ClawbotRuntimeConfig,
  ManagedEndpointStatus,
  ManagedServiceAction,
  ManagedServiceStatus,
  OpenclawUsageSnapshot,
} from '../../lib/tauri';

/** 服务矩阵面板的 props */
export interface ServiceMatrixProps {
  /** 所有托管服务列表 */
  services: ManagedServiceStatus[];
  /** 所有链路端点列表 */
  endpoints: ManagedEndpointStatus[];
  /** 各服务当前正在执行的操作（loading 状态） */
  serviceActionLoading: Record<string, ManagedServiceAction | null>;
  /** 触发单个服务操作 */
  onServiceAction: (label: string, action: ManagedServiceAction) => void;
  /** 触发单个服务的停止确认对话框 */
  onStopService: (label: string) => void;
}

/** 运行配置编辑面板的 props */
export interface ConfigEditorProps {
  /** 当前运行配置 */
  runtimeConfig: ClawbotRuntimeConfig;
  /** 更新单个配置字段 */
  onUpdateConfig: (key: keyof ClawbotRuntimeConfig, value: string) => void;
  /** 保存配置 */
  onSave: () => void;
  /** 保存并重启 ClawBot 链路 */
  onSaveAndRestart: () => void;
  /** 是否正在保存 */
  savingConfig: boolean;
  /** 是否正在保存并重启 */
  savingAndRestarting: boolean;
}

/** 多 Bot 矩阵面板的 props */
export interface BotMatrixProps {
  /** Bot 列表 */
  botMatrix: ClawbotBotMatrixEntry[];
  /** 就绪 Bot 数量 */
  readyBotCount: number;
}

/** 成本与配额快照面板的 props */
export interface UsagePanelProps {
  /** 用量快照 */
  usageSnapshot: OpenclawUsageSnapshot;
  /** 可读配额服务商数量 */
  usageProviderCount: number;
}

/** 日志查看面板的 props */
export interface LogViewerProps {
  /** 可选的服务列表（用于下拉选择） */
  services: ManagedServiceStatus[];
  /** 当前选中的日志标签 */
  selectedLogLabel: string;
  /** 切换日志标签 */
  onSelectLogLabel: (label: string) => void;
  /** 日志行列表 */
  serviceLogs: string[];
  /** 是否正在加载日志 */
  logsLoading: boolean;
  /** 是否自动刷新日志 */
  autoRefreshLogs: boolean;
  /** 切换自动刷新 */
  onToggleAutoRefresh: (enabled: boolean) => void;
  /** 手动刷新日志 */
  onRefreshLogs: () => void;
  /** 日志容器 ref，用于自动滚动 */
  logContainerRef: React.RefObject<HTMLDivElement>;
}

/** 顶部总控头的 props */
export interface ControlHeaderProps {
  /** 运行中服务数 */
  runningCount: number;
  /** 服务总数 */
  totalServices: number;
  /** 健康端点数 */
  healthyEndpointsCount: number;
  /** 端点总数 */
  totalEndpoints: number;
  /** 是否正在刷新 */
  refreshing: boolean;
  /** 全局操作是否正在加载 */
  allActionLoading: ManagedServiceAction | null;
  /** 刷新状态 */
  onRefresh: () => void;
  /** 全部启动 */
  onStartAll: () => void;
  /** 触发全部停止确认 */
  onStopAll: () => void;
  /** 全部重启 */
  onRestartAll: () => void;
}
