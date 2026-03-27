import { useState } from 'react';
import { Play, Square, RotateCcw, Stethoscope } from 'lucide-react';
import clsx from 'clsx';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '../../lib/tauri';

interface ServiceStatus {
  running: boolean;
  pid: number | null;
  port: number;
}

interface QuickActionsProps {
  status: ServiceStatus | null;
  loading: boolean;
  onStart: () => void;
  onStop: () => void;
  onRestart: () => void;
}

export function QuickActions({
  status,
  loading,
  onStart,
  onStop,
  onRestart,
}: QuickActionsProps) {
  const isRunning = status?.running || false;
  const [diagLoading, setDiagLoading] = useState(false);

  return (
    <Card className="bg-dark-700/50 border-dark-500 shadow-xl backdrop-blur-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg font-semibold text-white">快捷操作</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
          {/* 启动按钮 */}
          <button
            onClick={onStart}
            disabled={loading || isRunning}
            className={clsx(
              'flex flex-col items-center gap-3 p-4 rounded-xl transition-all',
              'border border-dark-500/50 shadow-sm',
              isRunning
                ? 'bg-dark-600/30 opacity-50 cursor-not-allowed'
                : 'bg-dark-600/50 hover:bg-green-500/10 hover:border-green-500/50 hover:shadow-green-500/20 active:scale-95'
            )}
          >
            <div
              className={clsx(
                'w-12 h-12 rounded-full flex items-center justify-center transition-colors',
                isRunning ? 'bg-dark-500' : 'bg-green-500/20'
              )}
            >
              <Play
                size={20}
                className={isRunning ? 'text-gray-500' : 'text-green-400'}
              />
            </div>
            <span
              className={clsx(
                'text-sm font-medium',
                isRunning ? 'text-gray-500' : 'text-gray-300'
              )}
            >
              启动
            </span>
          </button>

          {/* 停止按钮 */}
          <button
            onClick={onStop}
            disabled={loading || !isRunning}
            className={clsx(
              'flex flex-col items-center gap-3 p-4 rounded-xl transition-all',
              'border border-dark-500/50 shadow-sm',
              !isRunning
                ? 'bg-dark-600/30 opacity-50 cursor-not-allowed'
                : 'bg-dark-600/50 hover:bg-red-500/10 hover:border-red-500/50 hover:shadow-red-500/20 active:scale-95'
            )}
          >
            <div
              className={clsx(
                'w-12 h-12 rounded-full flex items-center justify-center transition-colors',
                !isRunning ? 'bg-dark-500' : 'bg-red-500/20'
              )}
            >
              <Square
                size={20}
                className={!isRunning ? 'text-gray-500' : 'text-red-400'}
              />
            </div>
            <span
              className={clsx(
                'text-sm font-medium',
                !isRunning ? 'text-gray-500' : 'text-gray-300'
              )}
            >
              停止
            </span>
          </button>

          {/* 重启按钮 */}
          <button
            onClick={onRestart}
            disabled={loading}
            className={clsx(
              'flex flex-col items-center gap-3 p-4 rounded-xl transition-all',
              'border border-dark-500/50 shadow-sm',
              'bg-dark-600/50 hover:bg-amber-500/10 hover:border-amber-500/50 hover:shadow-amber-500/20 active:scale-95'
            )}
          >
            <div className="w-12 h-12 rounded-full flex items-center justify-center bg-amber-500/20">
              <RotateCcw
                size={20}
                className={clsx('text-amber-400', loading && 'animate-spin')}
              />
            </div>
            <span className="text-sm font-medium text-gray-300">重启</span>
          </button>

          {/* 诊断按钮 */}
          <button
            onClick={async () => {
              try {
                setDiagLoading(true);
                const results = await api.runDoctor();
                const passed = results.filter(r => r.passed).length;
                const total = results.length;
                if (passed === total) {
                  toast.success(`诊断完成: ${total}/${total} 项通过`);
                } else {
                  toast.warning(`诊断完成: ${passed}/${total} 项通过, ${total - passed} 项需关注`);
                }
              } catch (e) {
                toast.error('诊断失败: ' + (e instanceof Error ? e.message : '未知错误'));
              } finally {
                setDiagLoading(false);
              }
            }}
            disabled={loading || diagLoading}
            className={clsx(
              'flex flex-col items-center gap-3 p-4 rounded-xl transition-all',
              'border border-dark-500/50 shadow-sm',
              'bg-dark-600/50 hover:bg-purple-500/10 hover:border-purple-500/50 hover:shadow-purple-500/20 active:scale-95'
            )}
          >
            <div className="w-12 h-12 rounded-full flex items-center justify-center bg-purple-500/20">
              <Stethoscope size={20} className={clsx('text-purple-400', diagLoading && 'animate-spin')} />
            </div>
            <span className="text-sm font-medium text-gray-300">诊断</span>
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
