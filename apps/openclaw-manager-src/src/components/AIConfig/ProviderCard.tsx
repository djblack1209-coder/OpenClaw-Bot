import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import {
  Loader2,
  Trash2,
  Star,
  ChevronDown,
  Cpu,
  Pencil,
} from 'lucide-react';
import clsx from 'clsx';
import type { OfficialProvider, ConfiguredProvider } from './types';

// ============ Provider 卡片 ============

interface ProviderCardProps {
  provider: ConfiguredProvider;
  officialProviders: OfficialProvider[];
  onSetPrimary: (modelId: string) => void;
  onRefresh: () => void;
  onEdit: (provider: ConfiguredProvider) => void;
}

export default function ProviderCard({ provider, officialProviders, onSetPrimary, onRefresh, onEdit }: ProviderCardProps) {
  const [expanded, setExpanded] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // 查找官方 Provider 信息
  const officialInfo = officialProviders.find(p => 
    provider.name.includes(p.id) || p.id === provider.name
  );

  // 检查是否使用了自定义地址
  const isCustomUrl = officialInfo && officialInfo.default_base_url && provider.base_url !== officialInfo.default_base_url;

  const handleDeleteClick = () => {
    setShowDeleteConfirm(true);
    setDeleteError(null);
  };

  const handleDeleteConfirm = async () => {
    setDeleting(true);
    setDeleteError(null);
    try {
      await invoke('delete_provider', { providerName: provider.name });
      setShowDeleteConfirm(false);
      onRefresh();
    } catch (e) {
      setDeleteError('删除失败: ' + String(e));
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteCancel = () => {
    setShowDeleteConfirm(false);
    setDeleteError(null);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-dark-700 rounded-xl border border-dark-500 overflow-hidden"
    >
      {/* 头部 */}
      <div
        className="flex items-center gap-3 p-4 cursor-pointer hover:bg-dark-600/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-xl">{officialInfo?.icon || '🔌'}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-white">{provider.name}</h3>
            {provider.has_api_key && (
              <span className="px-1.5 py-0.5 bg-green-500/20 text-green-400 text-xs rounded">
                已配置
              </span>
            )}
            {isCustomUrl && (
              <span className="px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 text-xs rounded">
                自定义地址
              </span>
            )}
          </div>
          <p className="text-xs text-gray-500 truncate">{provider.base_url}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">{provider.models.length} 模型</span>
          <motion.div animate={{ rotate: expanded ? 180 : 0 }}>
            <ChevronDown size={18} className="text-gray-500" />
          </motion.div>
        </div>
      </div>

      {/* 展开内容 */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-dark-600"
          >
            <div className="p-4 space-y-3">
              {/* API Key 信息 */}
              {provider.api_key_masked && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-500">API Key:</span>
                  <code className="px-2 py-0.5 bg-dark-600 rounded text-gray-400">
                    {provider.api_key_masked}
                  </code>
                </div>
              )}

              {/* 模型列表 */}
              <div className="space-y-2">
                {provider.models.map(model => (
                  <div
                    key={model.full_id}
                      className={clsx(
                      'flex items-center justify-between p-3 rounded-lg border transition-all',
                      model.is_primary
                        ? 'bg-claw-500/10 border-claw-500/50'
                        : 'bg-dark-600 border-dark-500'
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <Cpu size={16} className={model.is_primary ? 'text-claw-400' : 'text-gray-500'} />
                      <div>
                        <p className={clsx(
                            'text-sm font-medium',
                          model.is_primary ? 'text-white' : 'text-gray-300'
                        )}>
                          {model.name}
                          {model.is_primary && (
                            <span className="ml-2 text-xs text-claw-400">
                              <Star size={12} className="inline -mt-0.5" /> 主模型
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-gray-500">{model.full_id}</p>
                      </div>
                    </div>
                    {!model.is_primary && (
                      <button
                        onClick={() => onSetPrimary(model.full_id)}
                        className="text-xs text-gray-500 hover:text-claw-400 transition-colors"
                      >
                        设为主模型
                      </button>
                    )}
                  </div>
                ))}
              </div>

              {/* 删除确认对话框 */}
              {showDeleteConfirm && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg space-y-3"
                >
                  <p className="text-red-400 text-sm">
                    ⚠️ 确定要删除服务商 "{provider.name}" 吗？这将同时删除其下所有模型配置。
                  </p>
                  {deleteError && (
                    <p className="text-red-300 text-sm bg-red-500/20 p-2 rounded">
                      {deleteError}
                    </p>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={handleDeleteConfirm}
                      disabled={deleting}
                      className="btn-primary text-sm py-2 px-3 bg-red-500 hover:bg-red-600 flex items-center gap-1"
                    >
                      {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                      确认删除
                    </button>
                    <button
                      onClick={handleDeleteCancel}
                      disabled={deleting}
                      className="btn-secondary text-sm py-2 px-3"
                    >
                      取消
                    </button>
                  </div>
                </motion.div>
              )}

              {/* 操作按钮 */}
              {!showDeleteConfirm && (
                <div className="flex justify-end gap-4 pt-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onEdit(provider);
                    }}
                    className="flex items-center gap-1 text-sm text-claw-400 hover:text-claw-300 transition-colors"
                  >
                    <Pencil size={14} />
                    编辑服务商
                  </button>
                  <button
                    onClick={handleDeleteClick}
                    disabled={deleting}
                    className="flex items-center gap-1 text-sm text-red-400 hover:text-red-300 transition-colors"
                  >
                    {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    删除服务商
                  </button>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
