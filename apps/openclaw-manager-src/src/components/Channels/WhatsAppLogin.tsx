/**
 * WhatsApp 扫码登录组件
 * 处理 WhatsApp 的二维码扫码登录 + 状态轮询
 */
import { useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { toast } from 'sonner';
import { Loader2, QrCode, Check } from 'lucide-react';
import type { TestResult } from './channelDefinitions';

interface WhatsAppLoginProps {
  /** 刷新渠道列表 */
  onRefresh: () => Promise<void>;
  /** 回传测试/登录结果 */
  onTestResult: (result: TestResult) => void;
  /** 是否正在测试中（父组件控制） */
  testing: boolean;
  /** 触发快速测试 */
  onQuickTest: () => void;
}

export function WhatsAppLogin({ onRefresh, onTestResult, testing, onQuickTest }: WhatsAppLoginProps) {
  const [loginLoading, setLoginLoading] = useState(false);

  // WhatsApp 扫码登录
  const handleWhatsAppLogin = async () => {
    setLoginLoading(true);
    try {
      // 调用后端命令启动 WhatsApp 登录
      await invoke('start_channel_login', { channelType: 'whatsapp' });

      // 开始轮询检查登录状态
      const pollInterval = setInterval(async () => {
        try {
          const result = await invoke<{
            success: boolean;
            message: string;
          }>('test_channel', { channelType: 'whatsapp' });

          if (result.success) {
            clearInterval(pollInterval);
            clearTimeout(pollTimeout);
            setLoginLoading(false);
            // 刷新渠道列表
            await onRefresh();
            onTestResult({
              success: true,
              message: 'WhatsApp 登录成功！',
              error: null,
            });
          }
        } catch (e) {
          console.error('[Channels] WhatsApp login poll failed:', e);
        }
      }, 3000); // 每3秒检查一次

      // 60秒后停止轮询
      const pollTimeout = setTimeout(() => {
        clearInterval(pollInterval);
        setLoginLoading(false);
      }, 60000);

      toast.info('请在弹出的终端窗口中扫描二维码完成登录，登录成功后界面会自动更新');
    } catch (e) {
      toast.error('启动登录失败: ' + e);
      setLoginLoading(false);
    }
  };

  return (
    <div className="p-4 bg-green-500/10 rounded-xl border border-green-500/30">
      <div className="flex items-center gap-3 mb-3">
        <QrCode size={24} className="text-green-400" />
        <div>
          <p className="text-white font-medium">扫码登录</p>
          <p className="text-xs text-gray-400">WhatsApp 需要扫描二维码登录</p>
        </div>
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleWhatsAppLogin}
          disabled={loginLoading}
          className="flex-1 btn-secondary flex items-center justify-center gap-2"
        >
          {loginLoading ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <QrCode size={16} />
          )}
          {loginLoading ? '等待登录...' : '启动扫码登录'}
        </button>
        <button
          onClick={async () => {
            await onRefresh();
            onQuickTest();
          }}
          disabled={testing}
          className="btn-secondary flex items-center justify-center gap-2 px-4"
          title="刷新状态"
        >
          {testing ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Check size={16} />
          )}
        </button>
      </div>
      <p className="text-xs text-gray-500 mt-2 text-center">
        登录成功后点击右侧按钮刷新状态，或运行: openclaw channels login --channel whatsapp
      </p>
    </div>
  );
}
