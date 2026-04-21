import React from 'react';

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
  stack: string;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    message: '',
    stack: '',
  };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    const msg = error instanceof Error ? error.message : String(error);
    const stack = error instanceof Error ? error.stack || '' : '';
    return {
      hasError: true,
      message: msg,
      stack,
    };
  }

  componentDidCatch(error: unknown, errorInfo: React.ErrorInfo): void {
    console.error('[OpenClaw] 前端崩溃已捕获', error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen bg-dark-900 text-gray-100 flex items-center justify-center p-6">
        <div className="w-full max-w-3xl rounded-2xl border border-red-500/30 bg-dark-800 p-6">
          <h1 className="text-xl font-semibold text-red-300">OpenClaw 发生错误</h1>
          <p className="mt-2 text-sm text-gray-300">
            页面没有真正退出，已被错误边界接管。请先点击“刷新界面”，若仍复现，再把下面错误信息发给我。
          </p>

          <div className="mt-4 rounded-lg border border-dark-500 bg-dark-900 p-3 text-xs font-mono text-gray-300 whitespace-pre-wrap break-all">
            {this.state.message || '未知错误'}
            {this.state.stack ? `\n\n${this.state.stack}` : ''}
          </div>

          <div className="mt-5 flex gap-2">
            <button onClick={this.handleReload} className="btn-primary px-4 py-2">
              刷新界面
            </button>
          </div>
        </div>
      </div>
    );
  }
}
