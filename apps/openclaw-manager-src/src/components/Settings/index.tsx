import { useEffect, useState, useRef, useCallback } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { toast } from 'sonner';
import {
  User,
  Shield,
  Save,
  Loader2,
  FolderOpen,
  FileCode,
  Trash2,
  AlertTriangle,
  X,
  HardDrive,
} from 'lucide-react';
import { api, type ProjectContext } from '../../lib/tauri';
import { createLogger } from '@/lib/logger';
import { useAppStore } from '@/stores/appStore';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';

// 设置模块日志实例
const settingsLogger = createLogger('Settings');

interface InstallResult {
  success: boolean;
  message: string;
  error?: string;
}

interface SettingsProps {
  onEnvironmentChange?: () => void;
}

export function Settings({ onEnvironmentChange }: SettingsProps) {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = localStorage.getItem('openclaw-theme');
    return (saved === 'light' ? 'light' : 'dark');
  });

  // 初始化主题：页面加载时根据 localStorage 设置 DOM class
  useEffect(() => {
    if (theme === 'light') {
      document.documentElement.classList.add('light');
    } else {
      document.documentElement.classList.remove('light');
    }
  }, [theme]);

  const [identity, setIdentity] = useState({
    botName: 'OpenClaw',
    userName: '严总',
    timezone: 'Asia/Shanghai',
  });
  const [security, setSecurity] = useState({
    enableWhitelist: false,
    allowFileAccess: true,
  });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [projectContext, setProjectContext] = useState<ProjectContext | null>(null);
  const [openingSystemSettings, setOpeningSystemSettings] = useState(false);
  const [showUninstallConfirm, setShowUninstallConfirm] = useState(false);
  const [uninstalling, setUninstalling] = useState(false);
  const [uninstallResult, setUninstallResult] = useState<InstallResult | null>(null);

  // 未保存变更警告相关状态
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false);
  const pendingNavigationRef = useRef<string | null>(null);

  // 记录从服务端加载的初始值，用于检测是否有未保存修改
  const initialIdentityRef = useRef(identity);
  const initialSecurityRef = useRef(security);

  /** 判断当前表单是否有未保存的修改 */
  const isDirty = useCallback(() => {
    const initId = initialIdentityRef.current;
    const initSec = initialSecurityRef.current;
    return (
      identity.botName !== initId.botName ||
      identity.userName !== initId.userName ||
      identity.timezone !== initId.timezone ||
      security.enableWhitelist !== initSec.enableWhitelist ||
      security.allowFileAccess !== initSec.allowFileAccess
    );
  }, [identity, security]);

  const setNavigationGuard = useAppStore((s) => s.setNavigationGuard);
  const setCurrentPage = useAppStore((s) => s.setCurrentPage);

  // 注册导航守卫：离开设置页时检测未保存修改
  useEffect(() => {
    setNavigationGuard((targetPage) => {
      if (isDirty()) {
        // 有未保存修改，弹出确认对话框，暂停导航
        pendingNavigationRef.current = targetPage;
        setShowUnsavedDialog(true);
        return false; // 阻止导航
      }
      return true; // 允许导航
    });
    // 组件卸载时清除守卫
    return () => setNavigationGuard(null);
  }, [isDirty, setNavigationGuard]);

  useEffect(() => {
    const loadSettings = async () => {
      setLoading(true);
      try {
        const [context, settings] = await Promise.all([
          api.getProjectContext(),
          api.getAppSettings(),
        ]);
        setProjectContext(context);
        const loadedIdentity = {
          botName: settings.identity.bot_name,
          userName: settings.identity.user_name,
          timezone: settings.identity.timezone,
        };
        const loadedSecurity = {
          enableWhitelist: settings.security.enable_whitelist,
          allowFileAccess: settings.security.allow_file_access,
        };
        setIdentity(loadedIdentity);
        setSecurity(loadedSecurity);
        // 记录初始值用于脏状态检测
        initialIdentityRef.current = loadedIdentity;
        initialSecurityRef.current = loadedSecurity;
      } catch (e) {
        toast.error(`读取设置失败: ${String(e)}`);
      } finally {
        setLoading(false);
      }
    };

    loadSettings();
  }, []);

  const handleSave = async () => {
    // 验证 Bot 名称不能为空
    if (!identity.botName.trim()) {
      toast.error('Bot 名称不能为空');
      return;
    }
    setSaving(true);
    try {
      const message = await api.saveAppSettings({
        identity: {
          bot_name: identity.botName,
          user_name: identity.userName,
          timezone: identity.timezone,
        },
        security: {
          enable_whitelist: security.enableWhitelist,
          allow_file_access: security.allowFileAccess,
        },
      });
      toast.success(message);
      // 保存成功后，更新初始值基线（此时不再算"未保存"）
      initialIdentityRef.current = { ...identity };
      initialSecurityRef.current = { ...security };
    } catch (e) {
      toast.error(`保存失败: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const openConfigDir = async () => {
    try {
      const { open } = await import('@tauri-apps/plugin-shell');
      await open(projectContext?.config_dir ?? (await invoke<{ config_dir: string }>('get_system_info')).config_dir);
    } catch (e) {
      settingsLogger.error('打开目录失败:', e);
      toast.error('打开目录失败: ' + (e instanceof Error ? e.message : '未知错误'));
    }
  };

  const openFullDiskAccessSettings = async () => {
    setOpeningSystemSettings(true);
    try {
      const message = await api.openMacOSFullDiskAccessSettings();
      toast.success(message);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setOpeningSystemSettings(false);
    }
  };

  const handleUninstall = async () => {
    setUninstalling(true);
    setUninstallResult(null);
    try {
      const result = await invoke<InstallResult>('uninstall_openclaw');
      setUninstallResult(result);
      if (result.success) {
        // 通知环境状态变化，触发重新检查
        onEnvironmentChange?.();
        // 卸载成功后关闭确认框
        const timer = setTimeout(() => {
          setShowUninstallConfirm(false);
        }, 2000);
        // 组件卸载时清理定时器
        return () => clearTimeout(timer);
      }
    } catch (e) {
      setUninstallResult({
        success: false,
        message: '卸载过程中发生错误',
        error: String(e),
      });
    } finally {
      setUninstalling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        <span className="ml-3 text-gray-400">加载设置...</span>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto scroll-container pr-2">
      <div className="max-w-2xl space-y-6">
        {/* 身份配置 */}
        <div className="bg-dark-700 rounded-2xl p-6 border border-dark-500">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-claw-500/20 flex items-center justify-center">
              <User size={20} className="text-claw-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">身份配置</h3>
              <p className="text-xs text-gray-500">设置 AI 助手的名称和称呼</p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">
                AI 助手名称
              </label>
              <input
                type="text"
                value={identity.botName}
                onChange={(e) =>
                  setIdentity({ ...identity, botName: e.target.value })
                }
                placeholder="OpenClaw"
                className="input-base"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-2">
                你的称呼
              </label>
              <input
                type="text"
                value={identity.userName}
                onChange={(e) =>
                  setIdentity({ ...identity, userName: e.target.value })
                }
                placeholder="严总"
                className="input-base"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-2">时区</label>
              <select
                value={identity.timezone}
                onChange={(e) =>
                  setIdentity({ ...identity, timezone: e.target.value })
                }
                className="input-base"
              >
                <option value="Asia/Shanghai">Asia/Shanghai (北京时间)</option>
                <option value="Asia/Hong_Kong">Asia/Hong_Kong (香港时间)</option>
                <option value="Asia/Tokyo">Asia/Tokyo (东京时间)</option>
                <option value="America/New_York">
                  America/New_York (纽约时间)
                </option>
                <option value="America/Los_Angeles">
                  America/Los_Angeles (洛杉矶时间)
                </option>
                <option value="Europe/London">Europe/London (伦敦时间)</option>
                <option value="UTC">UTC</option>
              </select>
            </div>
          </div>
        </div>

        {/* 外观设置 */}
        <div className="bg-dark-800/60 rounded-xl p-5 border border-dark-600/50">
          <h3 className="text-sm font-semibold text-white/90 mb-3">外观</h3>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white/80">主题模式</p>
              <p className="text-xs text-white/40 mt-0.5">切换深色/浅色主题</p>
            </div>
            <button
              onClick={() => {
                const next = theme === 'dark' ? 'light' : 'dark';
                setTheme(next);
                localStorage.setItem('openclaw-theme', next);
                if (next === 'light') {
                  document.documentElement.classList.add('light');
                } else {
                  document.documentElement.classList.remove('light');
                }
              }}
              className="px-3 py-1.5 rounded-lg bg-dark-700 text-white/80 text-sm hover:bg-dark-600"
            >
              {theme === 'dark' ? '🌙 深色' : '☀️ 浅色'}
            </button>
          </div>
        </div>

        {/* 安全设置 */}
        <div className="bg-dark-700 rounded-2xl p-6 border border-dark-500">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
              <Shield size={20} className="text-amber-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">安全设置</h3>
              <p className="text-xs text-gray-500">权限和访问控制</p>
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-dark-600 rounded-lg">
              <div>
                <p className="text-sm text-white">启用白名单</p>
                <p className="text-xs text-gray-500">只允许白名单用户访问</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={security.enableWhitelist}
                  onChange={(e) =>
                    setSecurity({ ...security, enableWhitelist: e.target.checked })
                  }
                />
                <div className="w-11 h-6 bg-dark-500 peer-focus:ring-2 peer-focus:ring-claw-500/50 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-claw-500"></div>
              </label>
            </div>

            <div className="flex items-center justify-between p-4 bg-dark-600 rounded-lg">
              <div>
                <p className="text-sm text-white">文件访问权限</p>
                <p className="text-xs text-gray-500">允许 AI 读写本地文件</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  className="sr-only peer"
                  checked={security.allowFileAccess}
                  onChange={(e) =>
                    setSecurity({ ...security, allowFileAccess: e.target.checked })
                  }
                />
                <div className="w-11 h-6 bg-dark-500 peer-focus:ring-2 peer-focus:ring-claw-500/50 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-claw-500"></div>
              </label>
            </div>

            <div className="p-4 bg-dark-600 rounded-lg border border-dark-500">
              <p className="text-sm text-white mb-1">macOS 完全磁盘访问</p>
              <p className="text-xs text-gray-500 mb-3">系统权限无法自动授予，点击按钮可直接打开系统设置页面</p>
              <button
                onClick={openFullDiskAccessSettings}
                disabled={openingSystemSettings}
                className="btn-secondary flex items-center gap-2"
              >
                {openingSystemSettings ? <Loader2 size={16} className="animate-spin" /> : <HardDrive size={16} />}
                打开权限设置
              </button>
            </div>
          </div>
        </div>

        {/* 高级设置 */}
        <div className="bg-dark-700 rounded-2xl p-6 border border-dark-500">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
              <FileCode size={20} className="text-purple-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">高级设置</h3>
              <p className="text-xs text-gray-500">配置文件和目录</p>
            </div>
          </div>

          <div className="space-y-3">
            <button
              onClick={openConfigDir}
              className="w-full flex items-center gap-3 p-4 bg-dark-600 rounded-lg hover:bg-dark-500 transition-colors text-left"
            >
              <FolderOpen size={18} className="text-gray-400" />
              <div className="flex-1">
                <p className="text-sm text-white">打开配置目录</p>
                <p className="text-xs text-gray-500 break-all">{projectContext?.config_dir ?? '~/.openclaw'}</p>
              </div>
            </button>

            <div className="p-4 bg-dark-600 rounded-lg border border-dark-500 space-y-1">
              <p className="text-sm text-white">项目路径信息</p>
              <p className="text-xs text-gray-500 break-all">项目根目录: {projectContext?.project_base_dir ?? '加载中...'}</p>
              <p className="text-xs text-gray-500 break-all">工作区: {projectContext?.workspace_dir ?? '加载中...'}</p>
              <p className="text-xs text-gray-500 break-all">配置文件: {projectContext?.config_file ?? '加载中...'}</p>
              <p className="text-xs text-gray-500 break-all">本地设置: {projectContext?.settings_file ?? '加载中...'}</p>
            </div>
          </div>
        </div>

        {/* 数据管理 */}
        <div className="bg-dark-800/60 rounded-xl p-5 border border-dark-600/50">
          <h3 className="text-sm font-semibold text-white/90 mb-3">数据管理</h3>
          <div className="flex gap-3">
            <button
              onClick={async () => {
                try {
                  const settings = await api.getAppSettings();
                  const blob = new Blob([JSON.stringify(settings, null, 2)], { type: 'application/json' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `openclaw-settings-${new Date().toISOString().slice(0,10)}.json`;
                  a.click();
                  URL.revokeObjectURL(url);
                  toast.success('设置已导出');
                } catch (e) {
                  toast.error('导出失败');
                }
              }}
              className="px-4 py-2 rounded-lg bg-dark-700 text-white/80 text-sm hover:bg-dark-600 flex items-center gap-2"
            >
              导出设置
            </button>
            <label className="px-4 py-2 rounded-lg bg-dark-700 text-white/80 text-sm hover:bg-dark-600 cursor-pointer flex items-center gap-2">
              导入设置
              <input
                type="file"
                accept=".json"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  try {
                    const text = await file.text();
                    const settings = JSON.parse(text);
                    await api.saveAppSettings(settings);
                    toast.success('设置已导入，请刷新页面');
                    window.location.reload();
                  } catch (err) {
                    toast.error('导入失败：文件格式不正确');
                  }
                }}
              />
            </label>
          </div>
        </div>

        {/* 危险操作 */}
        <div className="bg-dark-700 rounded-2xl p-6 border border-red-900/30">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
              <AlertTriangle size={20} className="text-red-400" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">危险操作</h3>
              <p className="text-xs text-gray-500">以下操作不可撤销，请谨慎操作</p>
            </div>
          </div>

          <div className="space-y-3">
            <button
              onClick={() => setShowUninstallConfirm(true)}
              className="w-full flex items-center gap-3 p-4 bg-red-950/30 rounded-lg hover:bg-red-900/40 transition-colors text-left border border-red-900/30"
            >
              <Trash2 size={18} className="text-red-400" />
              <div className="flex-1">
                <p className="text-sm text-red-300">卸载 OpenClaw</p>
                <p className="text-xs text-red-400/70">从系统中移除 OpenClaw CLI 工具</p>
              </div>
            </button>
          </div>
        </div>

        {/* 卸载确认对话框 */}
        {showUninstallConfirm && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-dark-700 rounded-2xl p-6 border border-dark-500 max-w-md w-full mx-4 shadow-2xl">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
                    <AlertTriangle size={20} className="text-red-400" />
                  </div>
                  <h3 className="text-lg font-semibold text-white">确认卸载</h3>
                </div>
                <button
                  onClick={() => {
                    setShowUninstallConfirm(false);
                    setUninstallResult(null);
                  }}
                  className="text-gray-400 hover:text-white transition-colors"
                  aria-label="关闭对话框"
                >
                  <X size={20} />
                </button>
              </div>

              {!uninstallResult ? (
                <>
                  <p className="text-gray-300 mb-4">
                    确定要卸载 OpenClaw 吗？此操作将：
                  </p>
                  <ul className="text-sm text-gray-400 mb-6 space-y-2">
                    <li className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-red-400 rounded-full"></span>
                      停止正在运行的服务
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-red-400 rounded-full"></span>
                      移除 OpenClaw CLI 工具
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="w-1.5 h-1.5 bg-yellow-400 rounded-full"></span>
                      配置文件将被保留在 ~/.openclaw
                    </li>
                  </ul>

                  <div className="flex gap-3">
                    <button
                      onClick={() => setShowUninstallConfirm(false)}
                      className="flex-1 px-4 py-2.5 bg-dark-600 hover:bg-dark-500 text-white rounded-lg transition-colors"
                    >
                      取消
                    </button>
                    <button
                      onClick={handleUninstall}
                      disabled={uninstalling}
                      className="flex-1 px-4 py-2.5 bg-red-600 hover:bg-red-500 text-white rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                    >
                      {uninstalling ? (
                        <>
                          <Loader2 size={16} className="animate-spin" />
                          卸载中...
                        </>
                      ) : (
                        <>
                          <Trash2 size={16} />
                          确认卸载
                        </>
                      )}
                    </button>
                  </div>
                </>
              ) : (
                <div className={`p-4 rounded-lg ${uninstallResult.success ? 'bg-green-900/30 border border-green-800' : 'bg-red-900/30 border border-red-800'}`}>
                  <p className={`text-sm ${uninstallResult.success ? 'text-green-300' : 'text-red-300'}`}>
                    {uninstallResult.message}
                  </p>
                  {uninstallResult.error && (
                    <p className="text-xs text-red-400 mt-2 font-mono">
                      {uninstallResult.error}
                    </p>
                  )}
                  {uninstallResult.success && (
                    <p className="text-xs text-gray-400 mt-3">
                      对话框将自动关闭...
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 保存按钮 */}
        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving || loading}
            className="btn-primary flex items-center gap-2"
          >
            {saving ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Save size={16} />
            )}
            保存设置
          </button>
        </div>
      </div>

      {/* 离开页面前的未保存修改确认对话框 */}
      <ConfirmDialog
        open={showUnsavedDialog}
        onClose={() => {
          // 用户选择留在当前页
          setShowUnsavedDialog(false);
          pendingNavigationRef.current = null;
        }}
        onConfirm={() => {
          // 用户选择放弃修改并离开
          setShowUnsavedDialog(false);
          const target = pendingNavigationRef.current;
          pendingNavigationRef.current = null;
          if (target) {
            // 先清除守卫再导航，避免再次触发拦截
            setNavigationGuard(null);
            setCurrentPage(target as import('../../App').PageType);
          }
        }}
        title="有未保存的修改"
        description="你还有设置没有保存。离开此页面将丢失这些修改。"
        confirmText="放弃修改"
        cancelText="继续编辑"
        destructive
      />
    </div>
  );
}
