import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send, Bot, User, Mic, Paperclip, MessageSquare, Clock, Cpu, Zap, Brain,
  TrendingUp, Shield, BarChart3, Target, ScanSearch, PenTool, Sparkles,
  BookOpen, Palette, History, Plus, Trash2, Loader2,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import { api } from '../../lib/api';
import { toast } from '@/lib/notify';
import { useLanguage } from '../../i18n';
import { clawbotFetch } from '../../lib/tauri-core';

/* ========== 类型 ========== */
type AssistantMode = 'chat' | 'invest' | 'execute' | 'create';
interface ChatMessage { id: string; role: 'user' | 'ai'; content: string; timestamp: string }
interface SessionRecord { id: string; title: string; created_at: string; message_count: number }

/* ========== 模式配置（4 模式 × 6 快捷指令） ========== */
const I = 14; // 图标尺寸

/** 构建模式配置，接受 t() 以支持国际化 */
function getModeConfig(t: (key: string) => string): Record<AssistantMode, {
  label: string; colorHex: string;
  commands: { label: string; prefix: string; icon: React.ReactNode }[];
}> {
  return {
    chat:    { label: t('assistant.mode.chat'), colorHex: '#00d4ff', commands: [
      { label: t('assistant.cmd.brief'), prefix: '今日简报 ', icon: <BookOpen size={I}/> },
      { label: t('assistant.cmd.weather'), prefix: '天气查询 ', icon: <Sparkles size={I}/> },
      { label: t('assistant.cmd.translate'), prefix: '翻译文本: ', icon: <PenTool size={I}/> },
      { label: t('assistant.cmd.report'), prefix: '帮我写周报 ', icon: <Palette size={I}/> },
      { label: t('assistant.cmd.qa'), prefix: '知识问答: ', icon: <Brain size={I}/> },
      { label: t('assistant.cmd.schedule'), prefix: '日程安排 ', icon: <Clock size={I}/> },
    ]},
    invest:  { label: t('assistant.mode.invest'), colorHex: '#00ffaa', commands: [
      { label: t('assistant.cmd.aapl'), prefix: '分析AAPL ', icon: <TrendingUp size={I}/> },
      { label: t('assistant.cmd.holdings'), prefix: '查看持仓 ', icon: <BarChart3 size={I}/> },
      { label: t('assistant.cmd.backtest'), prefix: '回测策略 ', icon: <Target size={I}/> },
      { label: t('assistant.cmd.vote'), prefix: '大师投票 ', icon: <Brain size={I}/> },
      { label: t('assistant.cmd.risk'), prefix: '风控报告 ', icon: <Shield size={I}/> },
      { label: t('assistant.cmd.scan'), prefix: '市场扫描 ', icon: <ScanSearch size={I}/> },
    ]},
    execute: { label: t('assistant.mode.execute'), colorHex: '#fbbf24', commands: [
      { label: t('assistant.cmd.tweet'), prefix: '发布推文 ', icon: <Send size={I}/> },
      { label: t('assistant.cmd.batch'), prefix: '批量操作 ', icon: <Zap size={I}/> },
      { label: t('assistant.cmd.cron'), prefix: '定时任务 ', icon: <Clock size={I}/> },
      { label: t('assistant.cmd.export'), prefix: '数据导出 ', icon: <BarChart3 size={I}/> },
      { label: t('assistant.cmd.check'), prefix: '系统检查 ', icon: <Cpu size={I}/> },
      { label: t('assistant.cmd.logs'), prefix: '查看日志 ', icon: <History size={I}/> },
    ]},
    create:  { label: t('assistant.mode.create'), colorHex: '#a78bfa', commands: [
      { label: t('assistant.cmd.article'), prefix: '帮我写文章: ', icon: <PenTool size={I}/> },
      { label: t('assistant.cmd.image'), prefix: '生成图片: ', icon: <Palette size={I}/> },
      { label: t('assistant.cmd.video'), prefix: '视频脚本: ', icon: <Sparkles size={I}/> },
      { label: t('assistant.cmd.copy'), prefix: '营销文案: ', icon: <BookOpen size={I}/> },
      { label: t('assistant.cmd.code'), prefix: '代码生成: ', icon: <Cpu size={I}/> },
      { label: t('assistant.cmd.brain'), prefix: '头脑风暴: ', icon: <Brain size={I}/> },
    ]},
  };
}

/* ========== 工具函数 ========== */

/** 格式化时间戳为 HH:MM，无参数时返回当前时间 */
function fmtTime(ts?: string): string {
  const d = ts ? new Date(ts) : new Date();
  if (isNaN(d.getTime())) return ts || '';
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

/** 格式化会话创建时间（右侧列表用） */
function fmtSessionTime(ts: string): string {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  const t = fmtTime(ts);
  if (days === 0) return `今天 ${t}`;
  if (days === 1) return `昨天 ${t}`;
  return `${(d.getMonth() + 1).toString().padStart(2, '0')}/${d.getDate().toString().padStart(2, '0')} ${t}`;
}

/** 解析 SSE 流：兼容标准 SSE event/data 与旧格式 JSON */
async function readSSE(
  resp: Response,
  onChunk: (t: string) => void,
  onDone: () => void,
  onError: (e: string) => void,
  onStatus?: (t: string) => void,
) {
  if (!resp.body) {
    // 无流式 body，降级整体读取
    try { onChunk(await resp.text()); } catch (e) { onError(String(e)); }
    onDone(); return;
  }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop() || '';
      for (const part of parts) {
        const eventMatch = part.match(/^event:\s*(.+)$/m);
        const dataMatch = part.match(/^data:\s*(.+)$/m);
        if (!dataMatch) continue;
        const eventType = eventMatch?.[1]?.trim() || '';
        try {
          const p = JSON.parse(dataMatch[1]);
          if (eventType === 'chunk' && p.text) onChunk(p.text);
          else if (eventType === 'status' && p.text && onStatus) onStatus(p.text);
          else if (eventType === 'done') { onDone(); return; }
          else if (eventType === 'error') { onError(p.text || '未知错误'); return; }
          else if (p.type === 'chunk' && p.content) onChunk(p.content);
          else if (p.type === 'done') { onDone(); return; }
          else if (p.type === 'error') { onError(p.content || '未知错误'); return; }
        } catch {
          if (eventType === 'chunk') onChunk(dataMatch[1]);
        }
      }
    }
    // 处理残余 buffer
    if (buf.trim()) {
      const eventMatch = buf.trim().match(/^event:\s*(.+)$/m);
      const dataMatch = buf.trim().match(/^data:\s*(.+)$/m);
      const eventType = eventMatch?.[1]?.trim() || '';
      if (dataMatch) {
        try {
          const p = JSON.parse(dataMatch[1]);
          if (eventType === 'chunk' && p.text) onChunk(p.text);
          else if (p.type === 'chunk' && p.content) onChunk(p.content);
        } catch {
          if (eventType === 'chunk') onChunk(dataMatch[1]);
        }
      }
    }
    onDone();
  } catch (e) { onError(String(e)); }
}

/* ========== 组件 ========== */

export function Assistant() {
  const { t } = useLanguage();
  const MODE_CONFIG = getModeConfig(t);
  const [mode, setMode] = useState<AssistantMode>('chat');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [streamId, setStreamId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);       // 附件文件选择器
  const mediaRecorderRef = useRef<MediaRecorder | null>(null); // 语音录制器
  const audioChunksRef = useRef<Blob[]>([]);                 // 录音数据块缓冲
  const [isRecording, setIsRecording] = useState(false);     // 是否正在录音
  const [uploadingFile, setUploadingFile] = useState(false); // 是否正在上传附件
  const cfg = MODE_CONFIG[mode];

  // 自动滚动到底部
  useEffect(() => { scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }); }, [messages]);

  // 加载会话列表
  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try { setSessions((await api.conversationSessions(50))?.sessions || []); }
    catch (e) { console.error('加载会话列表失败:', e); }
    finally { setLoadingSessions(false); }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  // 选中会话 → 加载消息
  const selectSession = useCallback(async (sid: string) => {
    setActiveId(sid); setMessages([]);
    try {
      const raw: Array<{ role: string; content: string; timestamp?: string }> = (await api.conversationGet(sid))?.messages || [];
      setMessages(raw.map((m, i) => ({ id: `${sid}-${i}`, role: m.role === 'user' ? 'user' as const : 'ai' as const, content: m.content, timestamp: fmtTime(m.timestamp) })));
    } catch (e) { console.error('加载会话消息失败:', e); }
  }, []);

  // 新建对话
  const createSession = useCallback(async () => {
    try {
      const d = await api.conversationCreate(t('assistant.newChat'));
      if (d?.id) { setActiveId(d.id); setMessages([]); await loadSessions(); }
    } catch (e) { console.error('创建会话失败:', e); }
  }, [loadSessions]);

  // 删除对话
  const deleteSession = useCallback(async (sid: string, ev: React.MouseEvent) => {
    ev.stopPropagation();
    try {
      await api.conversationDelete(sid);
      if (sid === activeId) { setActiveId(null); setMessages([]); }
      await loadSessions();
    } catch (e) { console.error('删除会话失败:', e); }
  }, [activeId, loadSessions]);

  // 发送消息（核心逻辑）
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    // 无活跃会话时自动创建
    let sid = activeId;
    if (!sid) {
      try {
        const d = await api.conversationCreate(text.slice(0, 30));
        sid = d?.id; if (!sid) return;
        setActiveId(sid); loadSessions();
      } catch { return; }
    }

    const ts = fmtTime();
    const aiId = `a-${Date.now()}`;
    setMessages(p => [...p, { id: `u-${Date.now()}`, role: 'user', content: text, timestamp: ts }]);
    setInput(''); setLoading(true);
    // 占位 AI 消息，流式填充
    setMessages(p => [...p, { id: aiId, role: 'ai', content: '', timestamp: ts }]);
    setStreamId(aiId);

    const finish = () => { setLoading(false); setStreamId(null); };
    try {
      const resp = await clawbotFetch(
        `/api/v1/conversation/sessions/${sid}/send`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text }) },
        0, // 不限超时
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text().catch(() => 'Request failed')}`);
      await readSSE(resp,
        (chunk) => setMessages(p => p.map(m => m.id === aiId ? { ...m, content: (m.content.startsWith('💭') ? '' : m.content) + chunk } : m)),
        () => { finish(); if (sid) selectSession(sid); loadSessions(); },
        (err) => { setMessages(p => p.map(m => m.id === aiId ? { ...m, content: m.content || `⚠️ ${err}` } : m)); finish(); },
        (status) => setMessages(p => p.map(m => m.id === aiId && (!m.content || m.content.startsWith('💭')) ? { ...m, content: `💭 ${status}` } : m)),
      );
    } catch (e) {
      setMessages(p => p.map(m => m.id === aiId ? { ...m, content: `⚠️ ${e instanceof Error ? e.message : e}` } : m));
      finish();
    }
  }, [input, loading, activeId, loadSessions, selectSession]);

  // 附件上传处理：选择文件 → 上传到后端 → 提取文本 → 追加到输入框
  const handleFileUpload = useCallback(async (ev: React.ChangeEvent<HTMLInputElement>) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    // 重置 input 以便同一文件可重复选择
    ev.target.value = '';

    setUploadingFile(true);
    toast.info(`正在处理: ${file.name}...`, { channel: 'log' });

    try {
      const result = await api.conversationUpload(file);
      const text = result?.text || '';
      if (text) {
        // 将提取的文本追加到输入框
        const prefix = `[附件: ${file.name}]\n提取内容：${text}\n\n`;
        setInput(prev => prefix + prev);
        toast.success(`${file.name} 解析完成`, { channel: 'log' });
      } else {
        toast.warning(`${file.name} 未提取到有效内容`, { channel: 'notification' });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '未知错误';
      toast.error(`附件处理失败: ${msg}`, { channel: 'notification' });
    } finally {
      setUploadingFile(false);
    }
  }, []);

  // 语音录制切换：点击开始/停止录音
  const toggleRecording = useCallback(async () => {
    if (isRecording) {
      // 停止录音
      mediaRecorderRef.current?.stop();
      return;
    }

    // 开始录音：请求麦克风权限
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      });
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = async () => {
        // 停止所有音轨，释放麦克风
        stream.getTracks().forEach(track => track.stop());
        setIsRecording(false);

        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (audioBlob.size === 0) {
          toast.warning('录音内容为空', { channel: 'notification' });
          return;
        }

        toast.info('正在识别语音...', { channel: 'log' });
        try {
          const result = await api.conversationVoice(audioBlob);
          const text = result?.text || '';
          if (text) {
            setInput(prev => prev + text);
            toast.success('语音识别完成', { channel: 'log' });
          } else {
            toast.warning('语音识别未返回有效内容', { channel: 'notification' });
          }
        } catch (err) {
          const msg = err instanceof Error ? err.message : '未知错误';
          toast.error(`语音识别失败: ${msg}`, { channel: 'notification' });
        }
      };

      recorder.onerror = () => {
        stream.getTracks().forEach(track => track.stop());
        setIsRecording(false);
        toast.error('录音出错，请重试', { channel: 'notification' });
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
      toast.info('正在录音，再次点击停止...', { channel: 'log' });
    } catch (err) {
      // 用户拒绝麦克风权限或浏览器不支持
      const msg = err instanceof Error ? err.message : '未知错误';
      toast.error(`无法启动录音: ${msg}`, { channel: 'notification' });
    }
  }, [isRecording]);

  /* ========== 渲染 ========== */
  return (
    <div className="flex h-full gap-4 p-1">
      {/* 左侧主聊天区 */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* 模式切换 */}
        <div className="flex items-center gap-2 mb-3 flex-shrink-0">
          {(Object.keys(MODE_CONFIG) as AssistantMode[]).map(m => {
            const c = MODE_CONFIG[m], active = m === mode;
            return (
              <motion.button key={m} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }} onClick={() => setMode(m)}
                className={clsx('px-4 py-1.5 rounded-full text-xs font-medium font-display transition-all duration-200',
                  active ? 'text-[var(--bg-base)]' : 'text-[var(--text-secondary)] border border-[var(--glass-border)] hover:border-[var(--glass-border-hover)]')}
                style={active ? { background: c.colorHex, boxShadow: `0 0 16px ${c.colorHex}33` } : undefined}
              >{c.label}</motion.button>
            );
          })}
          <div className="ml-auto flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: cfg.colorHex }} />
            <span className="text-[10px] font-mono text-[var(--text-tertiary)]">{t('common.online')}</span>
          </div>
        </div>

        {/* 消息区域 */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto pr-1 space-y-3 scrollbar-thin scrollbar-thumb-white/10">
          {messages.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center h-full text-center opacity-40">
              <Bot size={40} className="mb-3 text-[var(--text-tertiary)]" />
              <p className="text-sm text-[var(--text-tertiary)]">{activeId ? t('assistant.sendToStart') : t('assistant.selectOrCreate')}</p>
            </div>
          )}
          <AnimatePresence initial>
            {messages.map((msg, i) => (
              <motion.div key={msg.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.04, 0.3), duration: 0.3 }}
                className={clsx('flex gap-2.5', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                {msg.role === 'ai' && (
                  <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1"
                    style={{ background: `${cfg.colorHex}18`, border: `1px solid ${cfg.colorHex}30` }}>
                    <Bot size={14} style={{ color: cfg.colorHex }} />
                  </div>
                )}
                <div className={clsx('abyss-card px-4 py-3 max-w-[75%] text-sm leading-relaxed', msg.role === 'user' && 'border-[var(--accent-cyan)]/20')}
                  style={msg.role === 'user' ? { borderColor: `${cfg.colorHex}30` } : undefined}>
                  <div className="whitespace-pre-wrap text-[var(--text-primary)]">
                    {msg.content}
                    {msg.id === streamId && <span className="inline-block w-1.5 h-4 ml-0.5 bg-current opacity-70 animate-pulse align-text-bottom" />}
                  </div>
                  <div className="mt-1.5 text-[10px] font-mono text-[var(--text-tertiary)] text-right">{msg.timestamp}</div>
                </div>
                {msg.role === 'user' && (
                  <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1 bg-[var(--accent-cyan)]/10 border border-[var(--accent-cyan)]/20">
                    <User size={14} className="text-[var(--accent-cyan)]" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
          {loading && !streamId && (
            <div className="flex gap-2.5 justify-start">
              <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center mt-1"
                style={{ background: `${cfg.colorHex}18`, border: `1px solid ${cfg.colorHex}30` }}>
                <Loader2 size={14} className="animate-spin" style={{ color: cfg.colorHex }} />
              </div>
              <div className="abyss-card px-4 py-3 text-sm text-[var(--text-tertiary)]">{t('assistant.thinking')}</div>
            </div>
          )}
        </div>

        {/* 输入区域 */}
        <div className="flex-shrink-0 mt-3">
          <div className={clsx('flex items-center gap-2 rounded-2xl px-4 py-2.5', 'bg-[var(--bg-card)] border border-[var(--glass-border)]', 'backdrop-blur-xl transition-all duration-300 focus-within:border-opacity-100')}
            onFocus={e => { e.currentTarget.style.borderColor = `${cfg.colorHex}55`; e.currentTarget.style.boxShadow = `0 0 20px ${cfg.colorHex}15`; }}
            onBlur={e => { e.currentTarget.style.borderColor = ''; e.currentTarget.style.boxShadow = ''; }}>
            {/* 隐藏的文件选择器 */}
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".pdf,.docx,.doc,.pptx,.xlsx,.png,.jpg,.jpeg,.tiff,.bmp,.gif,.ogg,.wav,.mp3,.m4a,.webm"
              onChange={handleFileUpload}
            />
            <button
              className={clsx(
                'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors',
                uploadingFile && 'animate-pulse'
              )}
              title="上传附件"
              disabled={uploadingFile}
              onClick={() => fileInputRef.current?.click()}
            >
              {uploadingFile ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
            </button>
            <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
              placeholder={loading ? t('assistant.aiReplying') : t('assistant.inputMessage')} disabled={loading}
              className={clsx('flex-1 bg-transparent text-sm text-[var(--text-primary)] font-body placeholder:text-[var(--text-tertiary)] outline-none disabled:opacity-50')} />
            <button
              className={clsx(
                'transition-colors',
                isRecording
                  ? 'text-red-400 animate-pulse'
                  : 'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
              )}
              title={isRecording ? '停止录音' : '语音输入'}
              onClick={toggleRecording}
            >
              <Mic size={16} />
            </button>
            <motion.button whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} onClick={handleSend} disabled={loading || !input.trim()}
              className="w-8 h-8 rounded-xl flex items-center justify-center transition-colors disabled:opacity-40"
              style={{ background: input.trim() && !loading ? cfg.colorHex : 'rgba(255,255,255,0.06)', color: input.trim() && !loading ? 'var(--bg-base)' : 'var(--text-tertiary)' }}>
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </motion.button>
          </div>
        </div>
      </div>

      {/* 右侧面板 */}
      <div className="w-[280px] flex-shrink-0 flex flex-col gap-3 overflow-y-auto">
        {/* 快捷指令 */}
        <div className="abyss-card p-4">
          <h3 className="text-label text-xs font-display mb-3 flex items-center gap-1.5">
            <Zap size={12} style={{ color: cfg.colorHex }} /> {t('assistant.shortcuts')}
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {cfg.commands.map(cmd => (
              <motion.button key={cmd.label} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                onClick={() => setInput(p => cmd.prefix + p)}
                className={clsx('flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-mono', 'bg-white/[0.03] border border-[var(--glass-border)] hover:border-opacity-100 transition-all duration-200', 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]')}
                onMouseEnter={e => { e.currentTarget.style.borderColor = `${cfg.colorHex}40`; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = ''; }}>
                {cmd.icon}{cmd.label}
              </motion.button>
            ))}
          </div>
        </div>

        {/* 会话历史 */}
        <div className="abyss-card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-label text-xs font-display flex items-center gap-1.5">
              <History size={12} className="text-[var(--text-tertiary)]" /> {t('assistant.sessionHistory')}
            </h3>
            <motion.button whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} onClick={createSession}
              className="w-6 h-6 rounded-lg flex items-center justify-center bg-white/[0.05] hover:bg-white/[0.1] transition-colors" title={t('assistant.newChat')}>
              <Plus size={12} className="text-[var(--text-secondary)]" />
            </motion.button>
          </div>
          <div className="space-y-1.5">
            {loadingSessions && sessions.length === 0 && (
              <div className="flex items-center justify-center py-4"><Loader2 size={16} className="animate-spin text-[var(--text-tertiary)]" /></div>
            )}
            {!loadingSessions && sessions.length === 0 && (
              <div className="text-center py-4 text-[10px] text-[var(--text-tertiary)]">{t('assistant.noSessions')}</div>
            )}
            {sessions.map((s, i) => (
              <motion.div key={s.id} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}
                onClick={() => selectSession(s.id)}
                className={clsx('group flex items-start justify-between gap-2 px-3 py-2.5 rounded-xl cursor-pointer hover:bg-white/[0.03] transition-colors duration-200',
                  s.id === activeId && 'bg-white/[0.05] border border-white/[0.06]')}>
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-[var(--text-primary)] truncate">{s.title}</div>
                  <div className="text-[10px] font-mono text-[var(--text-tertiary)] mt-0.5">{fmtSessionTime(s.created_at)}</div>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0 mt-0.5">
                  <MessageSquare size={10} className="text-[var(--text-tertiary)]" />
                  <span className="text-[10px] font-mono text-[var(--text-tertiary)]">{s.message_count}</span>
                  <button onClick={e => deleteSession(s.id, e)} className="opacity-0 group-hover:opacity-100 transition-opacity ml-1 text-[var(--text-tertiary)] hover:text-red-400" title={t('assistant.deleteSession')}>
                    <Trash2 size={10} />
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* 系统信息 */}
        <div className="abyss-card p-4">
          <h3 className="text-label text-xs font-display mb-3 flex items-center gap-1.5">
            <Cpu size={12} className="text-[var(--text-tertiary)]" /> {t('assistant.systemInfo')}
          </h3>
          <div className="space-y-2.5">
            {[
              { label: t('assistant.currentMode'), value: cfg.label, color: cfg.colorHex },
              { label: t('assistant.sessionCount'), value: String(sessions.length), color: '#00ffaa' },
              { label: t('assistant.currentMessages'), value: String(messages.length), color: '#fbbf24' },
              { label: t('assistant.status'), value: loading ? t('assistant.replying') : t('assistant.idle'), color: loading ? '#fbbf24' : '#00ffaa' },
            ].map(it => (
              <div key={it.label} className="flex items-center justify-between">
                <span className="text-[11px] text-[var(--text-tertiary)]">{it.label}</span>
                <span className="text-xs font-mono font-medium" style={{ color: it.color }}>{it.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
