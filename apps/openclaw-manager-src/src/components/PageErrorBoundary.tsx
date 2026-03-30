import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * 页面级错误边界状态
 * 与应用级 ErrorBoundary 不同，此组件只隔离单个页面的崩溃，
 * 侧边栏和顶栏保持可用，用户可以切换到其他页面。
 */
interface PageErrorBoundaryState {
  hasError: boolean;
  message: string;
}

interface PageErrorBoundaryProps {
  children: React.ReactNode;
  /** 页面名称，用于展示错误信息 */
  pageName?: string;
}

export class PageErrorBoundary extends React.Component<PageErrorBoundaryProps, PageErrorBoundaryState> {
  state: PageErrorBoundaryState = {
    hasError: false,
    message: '',
  };

  static getDerivedStateFromError(error: unknown): PageErrorBoundaryState {
    const msg = error instanceof Error ? error.message : String(error);
    return { hasError: true, message: msg };
  }

  componentDidCatch(error: unknown, errorInfo: React.ErrorInfo): void {
    // 页面级崩溃日志，包含页面名称便于排查
    console.error(
      `[PageErrorBoundary] 页面 "${this.props.pageName ?? '未知'}" 发生崩溃`,
      error,
      errorInfo,
    );
  }

  /** 重置错误状态，重新渲染子组件 */
  handleRetry = () => {
    this.setState({ hasError: false, message: '' });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    // 内联恢复卡片 — 不占满整屏，侧边栏/顶栏仍可用
    return (
      <div className="h-full flex items-center justify-center p-6">
        <div className="w-full max-w-md rounded-2xl border border-red-500/30 bg-dark-800 p-6 text-center">
          <div className="mx-auto w-12 h-12 rounded-xl bg-red-500/20 flex items-center justify-center mb-4">
            <AlertTriangle size={24} className="text-red-400" />
          </div>

          <h2 className="text-lg font-semibold text-red-300 mb-2">
            {this.props.pageName ? `「${this.props.pageName}」页面出错了` : '当前页面出错了'}
          </h2>
          <p className="text-sm text-gray-400 mb-4">
            这个页面遇到了问题，但其他页面不受影响。你可以点击下方按钮重试，或切换到其他页面继续使用。
          </p>

          <details className="text-left mb-4">
            <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 transition-colors">
              查看错误详情
            </summary>
            <pre className="mt-2 text-xs font-mono text-gray-500 bg-dark-900 rounded-lg p-3 whitespace-pre-wrap break-all border border-dark-600">
              {this.state.message || '未知错误'}
            </pre>
          </details>

          <button
            onClick={this.handleRetry}
            className="btn-primary inline-flex items-center gap-2 px-4 py-2"
          >
            <RefreshCw size={16} />
            重试
          </button>
        </div>
      </div>
    );
  }
}
