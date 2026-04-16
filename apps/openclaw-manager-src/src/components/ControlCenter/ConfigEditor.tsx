/**
 * ClawBot 运行配置编辑面板 — 表单字段 + 保存/重启按钮
 */
import { Loader2, Power, Save, Settings2 } from 'lucide-react';
import {
  getFieldHint,
  getFieldLabel,
  getFieldPlaceholder,
} from './constants';
import type { ClawbotRuntimeConfig } from '../../lib/tauri';
import type { ConfigEditorProps } from './types';

/** 单个配置字段渲染 */
function ConfigField({
  fieldKey,
  value,
  onChange,
}: {
  fieldKey: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const hint = getFieldHint(fieldKey);
  return (
    <div>
      <label className="block text-sm text-gray-300 mb-1">{getFieldLabel(fieldKey)}</label>
      {hint && <p className="text-xs text-gray-500 mb-2">{hint}</p>}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input-base"
        placeholder={getFieldPlaceholder(fieldKey)}
      />
    </div>
  );
}

export function ConfigEditor({
  runtimeConfig,
  onUpdateConfig,
  onSave,
  onSaveAndRestart,
  savingConfig,
  savingAndRestarting,
}: ConfigEditorProps) {
  /** 更新指定字段的快捷方法 */
  const update = (key: keyof ClawbotRuntimeConfig) => (value: string) => {
    onUpdateConfig(key, value);
  };

  return (
    <div className="bg-dark-700 rounded-2xl border border-dark-500 p-6">
      <div className="flex items-center gap-2 mb-4">
        <Settings2 size={18} className="text-accent-amber" />
        <h3 className="text-lg font-semibold text-white">ClawBot 运行配置</h3>
      </div>

      <div className="space-y-4">
        {/* G4F / Kiro 地址 */}
        <ConfigField fieldKey="G4F_BASE_URL" value={runtimeConfig.G4F_BASE_URL} onChange={update('G4F_BASE_URL')} />
        <ConfigField fieldKey="KIRO_BASE_URL" value={runtimeConfig.KIRO_BASE_URL} onChange={update('KIRO_BASE_URL')} />

        {/* IBKR 连接参数 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ConfigField fieldKey="IBKR_HOST" value={runtimeConfig.IBKR_HOST} onChange={update('IBKR_HOST')} />
          <ConfigField fieldKey="IBKR_PORT" value={runtimeConfig.IBKR_PORT} onChange={update('IBKR_PORT')} />
          <ConfigField fieldKey="IBKR_ACCOUNT" value={runtimeConfig.IBKR_ACCOUNT} onChange={update('IBKR_ACCOUNT')} />
          <ConfigField fieldKey="IBKR_BUDGET" value={runtimeConfig.IBKR_BUDGET} onChange={update('IBKR_BUDGET')} />
        </div>

        {/* IBKR 自动启动 + 启停命令 */}
        <div className="bg-dark-800 rounded-xl border border-dark-600 p-3 space-y-3">
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={(runtimeConfig.IBKR_AUTOSTART || 'true').toLowerCase() === 'true'}
              onChange={(e) => onUpdateConfig('IBKR_AUTOSTART', e.target.checked ? 'true' : 'false')}
              className="w-4 h-4 rounded"
            />
            全部启动/重启时自动拉起 IBKR
          </label>
          <ConfigField fieldKey="IBKR_START_CMD" value={runtimeConfig.IBKR_START_CMD} onChange={update('IBKR_START_CMD')} />
          <ConfigField fieldKey="IBKR_STOP_CMD" value={runtimeConfig.IBKR_STOP_CMD} onChange={update('IBKR_STOP_CMD')} />
        </div>

        {/* 通知频道 */}
        <ConfigField fieldKey="NOTIFY_CHAT_ID" value={runtimeConfig.NOTIFY_CHAT_ID} onChange={update('NOTIFY_CHAT_ID')} />

        {/* 操作按钮 */}
        <div className="pt-2 flex flex-wrap gap-2">
          <button
            onClick={onSave}
            disabled={savingConfig || savingAndRestarting}
            className="btn-secondary flex items-center gap-2"
          >
            {savingConfig ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            保存配置
          </button>
          <button
            onClick={onSaveAndRestart}
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
      </div>
    </div>
  );
}
