import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import {
  Loader2,
  Plus,
  Star,
  Sparkles,
  Zap,
  CheckCircle,
  XCircle,
  Cpu,
  Server,
} from 'lucide-react';
import clsx from 'clsx';
import { toast } from 'sonner';
import { aiLogger } from '../../lib/logger';
import { api, isTauri, type ProjectContext } from '../../lib/tauri';
import ProviderDialog from './ProviderDialog';
import ProviderCard from './ProviderCard';
import type {
  OfficialProvider,
  ConfiguredProvider,
  AIConfigOverview,
  AITestResult,
} from './types';

// 重新导出类型，方便外部使用
export type {
  SuggestedModel,
  OfficialProvider,
  ConfiguredModel,
  ConfiguredProvider,
  AIConfigOverview,
  ModelConfig,
  AITestResult,
} from './types';

// ============ 主组件 ============

export function AIConfig() {
  const [loading, setLoading] = useState(true);
  const [officialProviders, setOfficialProviders] = useState<OfficialProvider[]>([]);
  const [aiConfig, setAiConfig] = useState<AIConfigOverview | null>(null);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [editingProvider, setEditingProvider] = useState<ConfiguredProvider | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<AITestResult | null>(null);
  const [projectContext, setProjectContext] = useState<ProjectContext | null>(null);

  const handleEditProvider = (provider: ConfiguredProvider) => {
    setEditingProvider(provider);
    setShowAddDialog(true);
  };

  const handleCloseDialog = () => {
    setShowAddDialog(false);
    setEditingProvider(null);
  };

  const runAITest = async () => {
    aiLogger.action('测试 AI 连接');
    if (!isTauri()) {
      toast.error('请通过 OpenClaw 桌面应用启动后使用此功能');
      return;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const result = await invoke<AITestResult>('test_ai_connection');
      setTestResult(result);
      if (result.success) {
        aiLogger.info(`✅ AI 连接测试成功，延迟: ${result.latency_ms}ms`);
      } else {
        aiLogger.warn(`❌ AI 连接测试失败: ${result.error}`);
      }
    } catch (e) {
      aiLogger.error('AI 测试失败', e);
      setTestResult({
        success: false,
        provider: 'unknown',
        model: 'unknown',
        response: null,
        error: String(e),
        latency_ms: null,
      });
    } finally {
      setTesting(false);
    }
  };

  const loadData = useCallback(async () => {
    aiLogger.info('AIConfig 组件加载数据...');
    setError(null);
    
    // 非 Tauri 环境下优雅降级：显示空状态而非错误
    if (!isTauri()) {
      aiLogger.warn('不在 Tauri 环境中，AI 配置使用离线模式');
      setLoading(false);
      return;
    }
    
    try {
      const [officials, config] = await Promise.all([
        invoke<OfficialProvider[]>('get_official_providers'),
        invoke<AIConfigOverview>('get_ai_config'),
      ]);
      setOfficialProviders(officials);
      setAiConfig(config);
      try {
        const context = await api.getProjectContext();
        setProjectContext(context);
      } catch (e) {
        aiLogger.debug('[AIConfig] 获取项目上下文失败:', e);
      }
      aiLogger.info(`加载完成: ${officials.length} 个官方服务商, ${config.configured_providers.length} 个已配置`);
    } catch (e) {
      aiLogger.error('加载 AI 配置失败', e);
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSetPrimary = async (modelId: string) => {
    try {
      await invoke('set_primary_model', { modelId });
      aiLogger.info(`主模型已设置为: ${modelId}`);
      toast.success('主模型已切换，重启后端服务后生效');
      loadData();
    } catch (e) {
      aiLogger.error('设置主模型失败', e);
      toast.error('设置失败: ' + e);
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
      <div className="max-w-4xl space-y-6">
        {/* 错误提示 */}
        {error && (
          <div className="bg-red-500/20 border border-red-500/50 rounded-xl p-4 text-red-300">
            <p className="font-medium mb-1">加载配置失败</p>
            <p className="text-sm text-red-400">{error}</p>
            <button 
              onClick={loadData}
              className="mt-2 text-sm text-red-300 hover:text-white underline"
            >
              重试
            </button>
          </div>
        )}

        {/* 概览卡片 */}
        <div className="bg-gradient-to-br from-dark-700 to-dark-800 rounded-2xl p-6 border border-dark-500">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold text-white flex items-center gap-2">
                <Sparkles size={22} className="text-claw-400" />
                AI 模型配置
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                管理 OpenClaw 使用的 AI 服务商、主模型和统一号池接入
              </p>
            </div>
            <button
              onClick={() => setShowAddDialog(true)}
              className="btn-primary flex items-center gap-2"
            >
              <Plus size={16} />
              添加服务商
            </button>
          </div>

          {/* 主模型显示 */}
          <div className="bg-dark-600/50 rounded-xl p-4 flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-claw-500/20 flex items-center justify-center">
              <Star size={24} className="text-claw-400" />
            </div>
            <div className="flex-1">
              <p className="text-sm text-gray-400">当前主模型</p>
              {aiConfig?.primary_model ? (
                <p className="text-lg font-medium text-white">{aiConfig.primary_model}</p>
              ) : (
                <p className="text-lg text-gray-500">未设置</p>
              )}
            </div>
            <div className="text-right mr-4">
              <p className="text-sm text-gray-500">
                {aiConfig?.configured_providers.length || 0} 个服务商配置
              </p>
              <p className="text-sm text-gray-500">
                {aiConfig?.available_models.length || 0} 个可用模型
              </p>
            </div>
            <button
              onClick={runAITest}
              disabled={testing || !aiConfig?.primary_model}
              className="btn-secondary flex items-center gap-2"
            >
              {testing ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                <Zap size={16} />
              )}
              测试连接
            </button>
          </div>

          <div className="mt-4 rounded-xl border border-dark-500 bg-dark-800/40 p-4 text-sm text-gray-400 space-y-1.5">
            <p className="text-white font-medium">当前项目号池口径</p>
            <p>主链：SiliconFlow / iflow / Groq / Gemini</p>
            <p>补位：Cerebras / OpenRouter / NVIDIA / Volcengine</p>
            <p>兜底：Mistral / Cohere / GPT_API_Free / g4f</p>
            <p>付费 Claude 不再自动兜底，只有显式 <code className="text-claw-400">/claude</code> 才会走。</p>
          </div>

          {/* AI 测试结果 */}
          {testResult && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={clsx(
                'mt-4 p-4 rounded-xl',
                testResult.success ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'
              )}
            >
              <div className="flex items-center gap-3 mb-2">
                {testResult.success ? (
                  <CheckCircle size={20} className="text-green-400" />
                ) : (
                  <XCircle size={20} className="text-red-400" />
                )}
                <div className="flex-1">
                  <p className={clsx('font-medium', testResult.success ? 'text-green-400' : 'text-red-400')}>
                    {testResult.success ? '连接成功' : '连接失败'}
                  </p>
                  {testResult.latency_ms && (
                    <p className="text-xs text-gray-400">响应时间: {testResult.latency_ms}ms</p>
                  )}
                </div>
                <button
                  onClick={() => setTestResult(null)}
                  className="text-gray-500 hover:text-white text-sm"
                >
                  关闭
                </button>
              </div>
              
              {testResult.response && (
                <div className="mt-2 p-3 bg-dark-700 rounded-lg">
                  <p className="text-xs text-gray-400 mb-1">AI 响应:</p>
                  <p className="text-sm text-white whitespace-pre-wrap">{testResult.response}</p>
                </div>
              )}
              
              {testResult.error && (
                <div className="mt-2 p-3 bg-red-500/10 rounded-lg">
                  <p className="text-xs text-red-400 mb-1">错误信息:</p>
                  <p className="text-sm text-red-300 whitespace-pre-wrap">{testResult.error}</p>
                </div>
              )}
            </motion.div>
          )}
        </div>

        {/* 已配置的服务商列表 */}
        <div className="space-y-4">
          <h3 className="text-lg font-medium text-white flex items-center gap-2">
            <Server size={18} className="text-gray-500" />
            已配置的服务商
          </h3>

          {aiConfig?.configured_providers.length === 0 ? (
            <div className="bg-dark-700 rounded-xl border border-dark-500 p-8 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-dark-600 flex items-center justify-center">
                <Plus size={24} className="text-gray-500" />
              </div>
              <p className="text-gray-400 mb-4">还没有配置任何 AI 服务商</p>
              <button
                onClick={() => setShowAddDialog(true)}
                className="btn-primary"
              >
                添加第一个服务商
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {aiConfig?.configured_providers.map(provider => (
                <ProviderCard
                  key={provider.name}
                  provider={provider}
                  officialProviders={officialProviders}
                  onSetPrimary={handleSetPrimary}
                  onRefresh={loadData}
                  onEdit={handleEditProvider}
                />
              ))}
            </div>
          )}
        </div>

        {/* 可用模型列表 */}
        {aiConfig && aiConfig.available_models.length > 0 && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white flex items-center gap-2">
              <Cpu size={18} className="text-gray-500" />
              可用模型列表
              <span className="text-sm font-normal text-gray-500">
                ({aiConfig.available_models.length} 个)
              </span>
            </h3>
            <div className="bg-dark-700 rounded-xl border border-dark-500 p-4">
              <div className="flex flex-wrap gap-2">
                {aiConfig.available_models.map(modelId => (
                  <span
                    key={modelId}
                    className={clsx(
                      'inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm',
                      modelId === aiConfig.primary_model
                        ? 'bg-claw-500/20 text-claw-300 border border-claw-500/30'
                        : 'bg-dark-600 text-gray-300'
                    )}
                  >
                    {modelId === aiConfig.primary_model && <Star size={12} />}
                    {modelId}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 配置说明 */}
        <div className="bg-dark-700/50 rounded-xl p-4 border border-dark-500">
          <h4 className="text-sm font-medium text-gray-400 mb-2">配置说明</h4>
          <ul className="text-sm text-gray-500 space-y-1">
            <li>• 服务商配置保存在 <code className="text-claw-400">~/.openclaw/openclaw.json</code></li>
            <li>• 当前项目: <code className="text-claw-400">{projectContext?.project_base_dir ?? '加载中...'}</code></li>
            <li>• 当前工作区: <code className="text-claw-400">{projectContext?.workspace_dir ?? '加载中...'}</code></li>
            <li>• 支持官方服务商（Anthropic、OpenAI、Kimi 等）和自定义 OpenAI/Anthropic 兼容接口</li>
            <li>• 主模型用于 Agent 的默认推理，可随时切换</li>
            <li>• 修改配置后需要重启服务生效</li>
          </ul>
        </div>
      </div>

      {/* 添加/编辑服务商对话框 */}
      <AnimatePresence>
        {showAddDialog && (
          <ProviderDialog
            officialProviders={officialProviders}
            onClose={handleCloseDialog}
            onSave={() => {
              loadData();
              toast.success('服务商配置已保存，重启后端服务后生效');
            }}
            editingProvider={editingProvider}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
