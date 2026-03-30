import { useEffect, useState } from 'react';
import { Monitor, Package, Folder, CheckCircle, XCircle, Sparkles } from 'lucide-react';
import { api, SystemInfo as SystemInfoType, SkillsStatus, isTauri } from '../../lib/tauri';
import { dashboardLogger } from '../../lib/logger';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function SystemInfo() {
  const [info, setInfo] = useState<SystemInfoType | null>(null);
  const [skillsStatus, setSkillsStatus] = useState<SkillsStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchInfo = async () => {
      if (!isTauri()) {
        setLoading(false);
        return;
      }
      try {
        const [sysInfo, skills] = await Promise.all([
          api.getSystemInfo(),
          api.getSkillsStatus().catch(() => null),
        ]);
        setInfo(sysInfo);
        setSkillsStatus(skills);
      } catch (e) {
        dashboardLogger.warn('获取系统信息失败', e);
      } finally {
        setLoading(false);
      }
    };
    fetchInfo();
  }, []);

  const getOSLabel = (os: string) => {
    switch (os) {
      case 'macos':
        return 'macOS';
      case 'windows':
        return 'Windows';
      case 'linux':
        return 'Linux';
      default:
        return os;
    }
  };

  if (loading) {
    return (
      <Card className="bg-dark-700/50 border-dark-500 shadow-xl backdrop-blur-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg font-semibold text-white">系统信息</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-3 mt-4">
            <div className="h-4 bg-dark-500/50 rounded w-1/2"></div>
            <div className="h-4 bg-dark-500/50 rounded w-2/3"></div>
            <div className="h-4 bg-dark-500/50 rounded w-1/3"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-dark-700/50 border-dark-500 shadow-xl backdrop-blur-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg font-semibold text-white">系统信息</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
          {/* 操作系统 */}
          <div className="flex items-center gap-3 p-3 rounded-lg bg-dark-800/50 border border-dark-600/50">
            <div className="w-10 h-10 rounded-lg bg-dark-600 flex items-center justify-center">
              <Monitor size={18} className="text-gray-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-500 font-medium">操作系统</p>
              <p className="text-sm text-white font-medium truncate">
                {info ? `${getOSLabel(info.os)} ${info.os_version}` : '--'}{' '}
                <span className="text-gray-500 text-xs font-normal">({info?.arch})</span>
              </p>
            </div>
          </div>

          {/* OpenClaw */}
          <div className="flex items-center gap-3 p-3 rounded-lg bg-dark-800/50 border border-dark-600/50">
            <div className="w-10 h-10 rounded-lg bg-dark-600 flex items-center justify-center">
              {info?.openclaw_installed ? (
                <CheckCircle size={18} className="text-green-400" />
              ) : (
                <XCircle size={18} className="text-red-400" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-500 font-medium">OpenClaw</p>
              <p className="text-sm text-white font-medium truncate">
                {info?.openclaw_installed
                  ? info.openclaw_version || '已安装'
                  : '未安装'}
              </p>
            </div>
          </div>

          {/* Skills */}
          <div className="flex items-center gap-3 p-3 rounded-lg bg-dark-800/50 border border-dark-600/50">
            <div className="w-10 h-10 rounded-lg bg-dark-600 flex items-center justify-center">
              <Sparkles size={18} className="text-purple-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-500 font-medium">技能模块</p>
              <p className="text-sm text-white font-medium truncate">
                {skillsStatus
                  ? `${skillsStatus.enabled}/${skillsStatus.total} 已启用`
                  : '--'}
              </p>
            </div>
          </div>

          {/* Node.js */}
          <div className="flex items-center gap-3 p-3 rounded-lg bg-dark-800/50 border border-dark-600/50">
            <div className="w-10 h-10 rounded-lg bg-dark-600 flex items-center justify-center">
              <Package size={18} className="text-green-500" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-500 font-medium">Node.js</p>
              <p className="text-sm text-white font-medium truncate">{info?.node_version || '--'}</p>
            </div>
          </div>

          {/* 配置目录 */}
          <div className="flex items-center gap-3 p-3 rounded-lg bg-dark-800/50 border border-dark-600/50 md:col-span-2">
            <div className="w-10 h-10 rounded-lg bg-dark-600 flex items-center justify-center shrink-0">
              <Folder size={18} className="text-amber-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-500 font-medium">配置目录</p>
              <p className="text-xs text-white font-mono truncate">
                {info?.config_dir || '--'}
              </p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
