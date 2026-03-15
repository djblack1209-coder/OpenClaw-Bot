import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import './styles/globals.css';
// 确保 logger 初始化（会在控制台显示启动信息）
import './lib/logger';

function escapeHtml(raw: string) {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderFatalScreen(title: string, detail: string) {
  const root = document.getElementById('root');
  if (!root) {
    return;
  }

  root.innerHTML = `
    <div class="min-h-screen bg-dark-900 text-gray-100 flex items-center justify-center p-6">
      <div class="w-full max-w-3xl rounded-2xl border border-red-500/30 bg-dark-800 p-6">
        <h1 class="text-xl font-semibold text-red-300">${escapeHtml(title)}</h1>
        <p class="mt-2 text-sm text-gray-300">已切换到全局兜底页。请把下面错误信息和触发步骤发给我，我继续追根因。</p>
        <div class="mt-4 rounded-lg border border-dark-500 bg-dark-900 p-3 text-xs font-mono text-gray-300 whitespace-pre-wrap break-all">${escapeHtml(detail || '未知错误')}</div>
        <div class="mt-5 flex gap-2">
          <button id="fatal-reload-btn" class="btn-primary px-4 py-2">刷新界面</button>
        </div>
      </div>
    </div>
  `;

  const reloadBtn = document.getElementById('fatal-reload-btn');
  reloadBtn?.addEventListener('click', () => window.location.reload());
}

window.addEventListener('error', (event) => {
  const message = event.error instanceof Error ? event.error.message : event.message;
  const stack = event.error instanceof Error ? event.error.stack || '' : '';
  console.error('[OpenClaw Manager] 全局错误已捕获', event.error || event.message);
  renderFatalScreen('OpenClaw Manager 遇到全局错误', `${message || '未知错误'}${stack ? `\n\n${stack}` : ''}`);
});

window.addEventListener('unhandledrejection', (event) => {
  const reason = event.reason instanceof Error ? `${event.reason.message}\n\n${event.reason.stack || ''}` : String(event.reason || '未知 Promise 错误');
  console.error('[OpenClaw Manager] 未处理 Promise 错误', event.reason);
  renderFatalScreen('OpenClaw Manager 遇到未处理异常', reason);
});

console.log(
  '%c🦞 OpenClaw Bot 启动',
  'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; font-size: 16px; padding: 8px 16px; border-radius: 4px; font-weight: bold;'
);
console.log(
  '%c提示: 打开开发者工具 (Cmd+Option+I / Ctrl+Shift+I) 可以查看详细日志',
  'color: #888; font-size: 12px;'
);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
