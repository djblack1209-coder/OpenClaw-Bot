import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import {
  Check,
  Eye,
  EyeOff,
  Loader2,
  Plus,
  Settings2,
  ExternalLink,
  ChevronRight,
  XCircle,
} from 'lucide-react';
import clsx from 'clsx';
import { aiLogger } from '../../lib/logger';
import type {
  OfficialProvider,
  ConfiguredProvider,
  ModelConfig,
} from './types';

// ============ 添加/编辑服务商对话框 ============

interface ProviderDialogProps {
  officialProviders: OfficialProvider[];
  onClose: () => void;
  onSave: () => void;
  // 编辑模式时传入现有配置
  editingProvider?: ConfiguredProvider | null;
}

export default function ProviderDialog({ officialProviders, onClose, onSave, editingProvider }: ProviderDialogProps) {
  const isEditing = !!editingProvider;
  const [step, setStep] = useState<'select' | 'configure'>(isEditing ? 'configure' : 'select');
  const [selectedOfficial, setSelectedOfficial] = useState<OfficialProvider | null>(() => {
    if (editingProvider) {
      return officialProviders.find(p => 
        editingProvider.name.includes(p.id) || p.id === editingProvider.name
      ) || null;
    }
    return null;
  });
  
  // 配置表单
  const [providerName, setProviderName] = useState(editingProvider?.name || '');
  const [baseUrl, setBaseUrl] = useState(editingProvider?.base_url || '');
  const [apiKey, setApiKey] = useState('');
  const [apiType, setApiType] = useState(() => {
    if (editingProvider) {
      const firstModel = editingProvider.models[0];
      return firstModel?.api_type || 'openai-completions';
    }
    return 'openai-completions';
  });
  const [showApiKey, setShowApiKey] = useState(false);
  const [selectedModels, setSelectedModels] = useState<string[]>(() => {
    if (editingProvider) {
      return editingProvider.models.map(m => m.id);
    }
    return [];
  });
  const [customModelId, setCustomModelId] = useState('');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [showCustomUrlWarning, setShowCustomUrlWarning] = useState(false);

  // 检查是否是官方 Provider 名字但使用了自定义地址
  const isCustomUrlWithOfficialName = (() => {
    const official = officialProviders.find(p => p.id === providerName);
    if (official && official.default_base_url && baseUrl !== official.default_base_url) {
      return true;
    }
    return false;
  })();
  
  const handleSelectOfficial = (provider: OfficialProvider) => {
    setSelectedOfficial(provider);
    setProviderName(provider.id);
    setBaseUrl(provider.default_base_url || '');
    setApiType(provider.api_type);
    // 预选推荐模型
    const recommended = provider.suggested_models.filter(m => m.recommended).map(m => m.id);
    setSelectedModels(recommended.length > 0 ? recommended : [provider.suggested_models[0]?.id].filter(Boolean));
    setFormError(null);
    setShowCustomUrlWarning(false);
    setStep('configure');
  };

  const handleSelectCustom = () => {
    setSelectedOfficial(null);
    setProviderName('');
    setBaseUrl('');
    setApiType('openai-completions');
    setSelectedModels([]);
    setFormError(null);
    setShowCustomUrlWarning(false);
    setStep('configure');
  };

  const toggleModel = (modelId: string) => {
    setFormError(null);
    setSelectedModels(prev => 
      prev.includes(modelId) 
        ? prev.filter(id => id !== modelId)
        : [...prev, modelId]
    );
  };

  const addCustomModel = () => {
    if (customModelId && !selectedModels.includes(customModelId)) {
      setFormError(null);
      setSelectedModels(prev => [...prev, customModelId]);
      setCustomModelId('');
    }
  };

  // 自动建议使用自定义名称
  const suggestedName = (() => {
    if (isCustomUrlWithOfficialName && selectedOfficial) {
      return `${selectedOfficial.id}-custom`;
    }
    return null;
  })();

  const handleApplySuggestedName = () => {
    if (suggestedName) {
      setProviderName(suggestedName);
    }
  };

  const handleSave = async (forceOverride: boolean = false) => {
    setFormError(null);
    
    if (!providerName.trim()) {
      setFormError('请填写服务商名称');
      return;
    }

    if (!baseUrl.trim()) {
      setFormError('请填写 API 地址');
      return;
    }

    // 验证需要 API Key 的服务商在新建时必须填写
    if (selectedOfficial?.requires_api_key && !apiKey.trim() && !isEditing) {
      setFormError('请填写 API Key');
      return;
    }

    if (selectedModels.length === 0) {
      setFormError('请至少选择一个模型');
      return;
    }

    // 如果使用官方名字但自定义了地址，给出警告
    if (isCustomUrlWithOfficialName && !forceOverride) {
      setShowCustomUrlWarning(true);
      return;
    }
    
    setSaving(true);
    setShowCustomUrlWarning(false);
    try {
      // 构建模型配置
      const models: ModelConfig[] = selectedModels.map(modelId => {
        const suggested = selectedOfficial?.suggested_models.find(m => m.id === modelId);
        // 编辑模式下，保留原有模型的配置
        const existingModel = editingProvider?.models.find(m => m.id === modelId);
        return {
          id: modelId,
          name: suggested?.name || existingModel?.name || modelId,
          api: apiType,
          input: ['text', 'image'],
          context_window: suggested?.context_window || existingModel?.context_window || 200000,
          max_tokens: suggested?.max_tokens || existingModel?.max_tokens || 8192,
          reasoning: false,
          cost: null,
        };
      });

      await invoke('save_provider', {
        providerName,
        baseUrl,
        apiKey: apiKey || null,
        apiType,
        models,
      });

      aiLogger.info(`✓ 服务商 ${providerName} 已${isEditing ? '更新' : '保存'}`);
      onSave();
      onClose();
    } catch (e) {
      aiLogger.error('保存服务商失败', e);
      setFormError('保存失败: ' + String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="bg-dark-800 rounded-2xl border border-dark-600 w-full max-w-2xl max-h-[85vh] overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="px-6 py-4 border-b border-dark-600 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            {isEditing ? <Settings2 size={20} className="text-claw-400" /> : <Plus size={20} className="text-claw-400" />}
            {isEditing 
              ? `编辑服务商: ${editingProvider?.name}` 
              : (step === 'select' ? '添加 AI 服务商' : `配置 ${selectedOfficial?.name || '自定义服务商'}`)}
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white" aria-label="关闭对话框">
            ✕
          </button>
        </div>

        {/* 内容 */}
        <div className="p-6 overflow-y-auto max-h-[calc(85vh-140px)]">
          <AnimatePresence mode="wait">
            {step === 'select' ? (
              <motion.div
                key="select"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="space-y-4"
              >
                {/* 官方服务商 */}
                <div className="space-y-3">
                  <h3 className="text-sm font-medium text-gray-400">官方服务商</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {officialProviders.map(provider => (
                <button
                  key={provider.id}
                        onClick={() => handleSelectOfficial(provider)}
                        className="flex items-center gap-3 p-4 rounded-xl bg-dark-700 border border-dark-500 hover:border-claw-500/50 hover:bg-dark-600 transition-all text-left group"
                >
                  <span className="text-2xl">{provider.icon}</span>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-white truncate">{provider.name}</p>
                          <p className="text-xs text-gray-500 truncate">
                            {provider.suggested_models.length} 个模型
                          </p>
                    </div>
                        <ChevronRight size={16} className="text-gray-500 group-hover:text-claw-400 transition-colors" />
                </button>
                    ))}
          </div>
        </div>

                {/* 自定义服务商 */}
                <div className="pt-4 border-t border-dark-600">
                  <button
                    onClick={handleSelectCustom}
                    className="w-full flex items-center justify-center gap-2 p-4 rounded-xl border-2 border-dashed border-dark-500 hover:border-claw-500/50 text-gray-400 hover:text-white transition-all"
                  >
                    <Settings2 size={18} />
                    <span>自定义服务商 (兼容 OpenAI/Anthropic API)</span>
                  </button>
                </div>
              </motion.div>
            ) : (
          <motion.div
                key="configure"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="space-y-5"
              >
                {/* 服务商名称 */}
                <div>
                  <label className="block text-sm text-gray-400 mb-2">
                    服务商名称
                    <span className="text-gray-600 text-xs ml-2">(用于配置标识，如 anthropic-custom)</span>
                  </label>
                  <input
                    type="text"
                    value={providerName}
                    onChange={e => { setFormError(null); setProviderName(e.target.value); }}
                    placeholder="如: anthropic-custom, my-openai"
                    className={clsx(
                      'input-base',
                      isCustomUrlWithOfficialName && 'border-yellow-500/50'
                    )}
                    disabled={isEditing}
                  />
                  {isEditing && (
                    <p className="text-xs text-gray-500 mt-1">
                      服务商名称不可修改，如需更改请删除后重新创建
                    </p>
                  )}
                  {isCustomUrlWithOfficialName && !isEditing && (
                    <div className="mt-2 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                      <p className="text-xs text-yellow-400">
                        ⚠️ 您使用的是官方服务商名称，但修改了 API 地址。建议使用不同的名称以避免配置冲突。
                      </p>
                      <button
                        type="button"
                        onClick={handleApplySuggestedName}
                        className="mt-1 text-xs text-yellow-300 hover:text-yellow-200 underline"
                      >
                        使用建议名称: {suggestedName}
                      </button>
                    </div>
                  )}
                </div>

                {/* API 地址 */}
                <div>
                  <label className="block text-sm text-gray-400 mb-2">API 地址</label>
                  <input
                    type="text"
                    value={baseUrl}
                    onChange={e => { setFormError(null); setBaseUrl(e.target.value); }}
                    placeholder="https://api.example.com/v1"
                    className="input-base"
                  />
                </div>

              {/* API Key */}
                <div>
                  <label className="block text-sm text-gray-400 mb-2">
                    API Key
                    {!selectedOfficial?.requires_api_key && (
                      <span className="text-gray-600 text-xs ml-2">(可选)</span>
                    )}
                  </label>
                  {/* 编辑模式下显示当前 API Key 状态 */}
                  {isEditing && editingProvider?.has_api_key && (
                    <div className="mb-2 flex items-center gap-2 text-sm">
                      <span className="text-gray-500">当前:</span>
                      <code className="px-2 py-0.5 bg-dark-600 rounded text-gray-400">
                        {editingProvider.api_key_masked}
                      </code>
                      <span className="text-green-400 text-xs">✓ 已配置</span>
                    </div>
                  )}
                  <div className="relative">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={apiKey}
                      onChange={e => setApiKey(e.target.value)}
                      placeholder={isEditing && editingProvider?.has_api_key 
                        ? "留空保持原有 API Key 不变，或输入新的 Key" 
                        : "sk-..."}
                      className="input-base pr-10"
                      aria-label="API 密钥"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
                      aria-label={showApiKey ? "隐藏密钥" : "显示密钥"}
                    >
                      {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                  {isEditing && editingProvider?.has_api_key && (
                    <p className="text-xs text-gray-500 mt-1">
                      💡 如果不需要更改 API Key，请保持为空
                    </p>
                  )}
                </div>

                {/* API 类型 */}
                <div>
                  <label className="block text-sm text-gray-400 mb-2">API 类型</label>
                  <select
                    value={apiType}
                    onChange={e => setApiType(e.target.value)}
                    className="input-base"
                  >
                    <option value="openai-completions">OpenAI 兼容 (openai-completions)</option>
                    <option value="anthropic-messages">Anthropic 兼容 (anthropic-messages)</option>
                  </select>
                </div>

                {/* 模型选择 */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                    选择模型
                    <span className="text-gray-600 text-xs ml-2">
                      (已选 {selectedModels.length} 个)
                    </span>
                  </label>
                  
                  {/* 预设模型 */}
                  {selectedOfficial && (
                    <div className="space-y-2 mb-3">
                      {selectedOfficial.suggested_models.map(model => (
                        <button
                          key={model.id}
                          onClick={() => toggleModel(model.id)}
                          className={clsx(
                            'w-full flex items-center justify-between p-3 rounded-lg border transition-all text-left',
                            selectedModels.includes(model.id)
                              ? 'bg-claw-500/20 border-claw-500'
                              : 'bg-dark-700 border-dark-500 hover:border-dark-400'
                          )}
                        >
                          <div>
                            <p className={clsx(
                              'text-sm font-medium',
                              selectedModels.includes(model.id) ? 'text-white' : 'text-gray-300'
                            )}>
                              {model.name}
                              {model.recommended && (
                                <span className="ml-2 text-xs text-claw-400">推荐</span>
                              )}
                            </p>
                            {model.description && (
                              <p className="text-xs text-gray-500 mt-0.5">{model.description}</p>
                            )}
                          </div>
                          {selectedModels.includes(model.id) && (
                            <Check size={16} className="text-claw-400" />
                          )}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* 自定义模型输入 */}
                  <div className="flex gap-2">
                  <input
                    type="text"
                      value={customModelId}
                      onChange={e => setCustomModelId(e.target.value)}
                      placeholder="输入自定义模型 ID"
                      className="input-base flex-1"
                      onKeyDown={e => e.key === 'Enter' && addCustomModel()}
                      aria-label="自定义模型 ID"
                    />
                    <button
                      onClick={addCustomModel}
                      disabled={!customModelId}
                      className="btn-secondary px-4"
                      aria-label="添加自定义模型"
                    >
                      <Plus size={16} />
                    </button>
                  </div>

                  {/* 已添加的自定义模型 */}
                  {selectedModels.filter(id => !selectedOfficial?.suggested_models.find(m => m.id === id)).length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedModels
                        .filter(id => !selectedOfficial?.suggested_models.find(m => m.id === id))
                        .map(modelId => (
                          <span
                            key={modelId}
                            className="inline-flex items-center gap-1 px-2 py-1 bg-dark-600 rounded-lg text-sm text-gray-300"
                          >
                            {modelId}
                            <button
                              onClick={() => toggleModel(modelId)}
                              className="text-gray-500 hover:text-red-400"
                              aria-label="移除模型"
                            >
                              ✕
                            </button>
                          </span>
                        ))}
                    </div>
                  )}
                </div>

                {/* 文档链接 */}
                {selectedOfficial?.docs_url && (
                  <a
                    href={selectedOfficial.docs_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm text-claw-400 hover:text-claw-300"
                  >
                    <ExternalLink size={14} />
                    查看官方文档
                  </a>
                )}

                {/* 表单错误提示 */}
                {formError && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg"
                  >
                    <p className="text-red-400 text-sm flex items-center gap-2">
                      <XCircle size={16} />
                      {formError}
                    </p>
                  </motion.div>
                )}

                {/* 自定义 URL 警告对话框 */}
                {showCustomUrlWarning && (
                  <motion.div
                    initial={{ opacity: 0, y: -10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg space-y-3"
                  >
                    <p className="text-yellow-400 text-sm">
                      ⚠️ 您使用的是官方 Provider 名称 "{providerName}"，但修改了 API 地址。
                      这可能导致配置被 OpenClaw 内置设置覆盖。
                    </p>
                    <p className="text-yellow-300 text-sm">
                      建议使用不同的名称，如 "{suggestedName}"
                    </p>
                    <div className="flex gap-2 pt-2">
                      <button
                        onClick={handleApplySuggestedName}
                        className="btn-secondary text-sm py-2 px-3"
                      >
                        使用建议名称
                      </button>
                      <button
                        onClick={() => handleSave(true)}
                        className="btn-primary text-sm py-2 px-3"
                      >
                        仍然保存
                      </button>
                      <button
                        onClick={() => setShowCustomUrlWarning(false)}
                        className="text-sm text-gray-400 hover:text-white px-3"
                      >
                        取消
                      </button>
                    </div>
                  </motion.div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
              </div>

        {/* 底部按钮 */}
        <div className="px-6 py-4 border-t border-dark-600 flex justify-between">
          {step === 'configure' && !isEditing && (
            <button
              onClick={() => setStep('select')}
              className="btn-secondary"
            >
              返回
            </button>
          )}
          <div className="flex-1" />
          <div className="flex gap-3">
            <button onClick={onClose} className="btn-secondary">
              取消
            </button>
            {step === 'configure' && !showCustomUrlWarning && (
              <button
                onClick={() => handleSave()}
                disabled={saving || !providerName || !baseUrl || selectedModels.length === 0}
                className="btn-primary flex items-center gap-2"
              >
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
                {isEditing ? '更新' : '保存'}
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
