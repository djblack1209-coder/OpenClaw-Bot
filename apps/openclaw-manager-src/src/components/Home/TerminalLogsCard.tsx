import { useRef, useEffect } from 'react';
import type { LogEntry } from './index';
import { isTauri } from '../../lib/tauri-core';
import { useLanguage } from '@/i18n';

interface Props {
  logs: LogEntry[];
}

/* 日志级别颜色映射 */
const levelColors: Record<string, string> = {
  INFO: 'var(--accent-cyan)',
  OK: 'var(--accent-green)',
  WARN: 'var(--accent-amber)',
  ERROR: 'var(--accent-red)',
};

/**
 * 终端日志卡片 — 模拟终端输出
 * 彩色时间戳 + 级别标签 + 模块名 + 消息
 */
export function TerminalLogsCard({ logs }: Props) {
  const { t } = useLanguage();
  const scrollRef = useRef<HTMLDivElement>(null);

  /* 新日志到达时自动滚动到底部 */
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0; // 最新在顶部
    }
  }, [logs.length]);

  return (
    <div className="abyss-card p-5 h-full flex flex-col" style={{ minHeight: '280px' }}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-label">{t('terminalLogs.title')}</span>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-disabled)' }}>
          {logs.length} {t('terminalLogs.count')}
        </span>
      </div>

      {/* 终端输出区域 */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto scroll-container rounded-lg p-3"
        style={{
          background: 'rgba(0, 0, 0, 0.3)',
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          lineHeight: '1.8',
          maxHeight: '260px',
        }}
      >
        {logs.length > 0 ? (
          logs.map((entry) => (
            <div key={entry.id} className="flex gap-2 whitespace-nowrap">
              {/* 时间戳 */}
              <span style={{ color: 'var(--text-disabled)' }}>[{entry.timestamp}]</span>
              {/* 级别 */}
              <span style={{ color: levelColors[entry.level] || 'var(--text-tertiary)' }}>
                [{entry.level.padEnd(5)}]
              </span>
              {/* 模块 */}
              <span style={{ color: 'var(--text-tertiary)' }}>[{entry.module}]</span>
              {/* 消息 */}
              <span
                className="truncate"
                style={{ color: 'var(--text-secondary)' }}
                title={entry.message}
              >
                {entry.message}
              </span>
            </div>
          ))
        ) : (
          /* 空状态 — 根据运行环境给出不同提示 */
          <div className="flex items-center justify-center h-full">
            <span className="font-mono text-xs" style={{ color: 'var(--text-disabled)' }}>
              {isTauri()
                ? t('terminalLogs.waiting')
                : t('terminalLogs.browserMode')}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
