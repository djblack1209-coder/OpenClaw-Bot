/**
 * AI 助手对话服务 — 封装后端会话 API + SSE 流式通信
 *
 * 所有 HTTP 请求通过 clawbotFetch 发送到 localhost:18790
 * SSE 流通过原生 fetch + ReadableStream 处理
 */

import { clawbotFetch } from '../lib/tauri';
import { toast } from '@/lib/notify';
import { useConversationStore, type SessionSummary, type Session, type Message } from '../stores/conversationStore';

/** 拉取会话列表 */
export async function fetchSessions(): Promise<SessionSummary[]> {
  const store = useConversationStore.getState();
  store.setLoadingSessions(true);
  try {
    const resp = await clawbotFetch('/api/v1/conversation/sessions?limit=50');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const sessions: SessionSummary[] = data.sessions ?? [];
    store.setSessions(sessions);
    return sessions;
  } catch (e) {
    console.error('获取会话列表失败:', e);
    toast.error('获取会话列表失败', { channel: 'notification' });
    return [];
  } finally {
    store.setLoadingSessions(false);
  }
}

/** 创建新会话 */
export async function createSession(title?: string): Promise<string | null> {
  try {
    const resp = await clawbotFetch(
      `/api/v1/conversation/sessions?title=${encodeURIComponent(title || '新对话')}`,
      { method: 'POST' }
    );
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const session = await resp.json();
    const store = useConversationStore.getState();
    store.setActiveSession(session.id);
    store.setMessages([]);
    // 刷新列表
    await fetchSessions();
    return session.id;
  } catch (e) {
    console.error('创建会话失败:', e);
    toast.error('创建会话失败', { channel: 'notification' });
    return null;
  }
}

/** 加载会话详情（含全部消息） */
export async function loadSession(sessionId: string): Promise<void> {
  const store = useConversationStore.getState();
  try {
    const resp = await clawbotFetch(`/api/v1/conversation/sessions/${sessionId}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const session: Session = await resp.json();
    store.setActiveSession(session.id);
    store.setMessages(session.messages ?? []);
  } catch (e) {
    console.error('加载会话详情失败:', e);
    toast.error('加载会话详情失败', { channel: 'notification' });
  }
}

/** 删除会话 */
export async function deleteSession(sessionId: string): Promise<void> {
  try {
    await clawbotFetch(`/api/v1/conversation/sessions/${sessionId}`, { method: 'DELETE' });
    const store = useConversationStore.getState();
    if (store.activeSessionId === sessionId) {
      store.clearActive();
    }
    await fetchSessions();
  } catch (e) {
    console.error('删除会话失败:', e);
    toast.error('删除会话失败', { channel: 'notification' });
  }
}

/**
 * 发送消息并处理 SSE 流式响应
 *
 * 流程：
 * 1. 前端立即显示用户消息
 * 2. 创建空的助手消息（streaming=true）
 * 3. 通过 SSE 接收 status/chunk/result/error/done 事件
 * 4. chunk 事件追加到助手消息
 * 5. done 事件标记流结束
 */
export async function sendMessage(sessionId: string, message: string): Promise<void> {
  const store = useConversationStore.getState();

  if (store.sending) return; // 防止重复发送
  store.setSending(true);
  store.setStatusText(null);

  // 1. 立即显示用户消息
  const userMsg: Message = {
    id: crypto.randomUUID().slice(0, 8),
    role: 'user',
    content: message,
    timestamp: new Date().toISOString(),
  };
  store.addMessage(userMsg);

  // 2. 创建空的助手消息占位
  const assistantMsg: Message = {
    id: crypto.randomUUID().slice(0, 8),
    role: 'assistant',
    content: '',
    timestamp: new Date().toISOString(),
    streaming: true,
  };
  store.addMessage(assistantMsg);

  try {
    // 3. 发起 SSE 请求（通过 clawbotFetch 发送，自动附加 API Token）
    // SSE 流式响应可能持续很长时间（AI 分析/搜索等），禁用超时
    const response = await clawbotFetch(
      `/api/v1/conversation/sessions/${sessionId}/send`,
      {
        method: 'POST',
        headers: {
          'Accept': 'text/event-stream',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message }),
      },
      0 // 禁用超时，SSE 流式响应不应被中断
    );

    if (!response.ok || !response.body) {
      throw new Error(`HTTP ${response.status}`);
    }

    // 4. 读取 SSE 流
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 按双换行分割 SSE 事件
      const events = buffer.split('\n\n');
      buffer = events.pop() ?? ''; // 最后一段可能不完整，保留

      for (const eventStr of events) {
        if (!eventStr.trim()) continue;

        const lines = eventStr.split('\n');
        let eventType = '';
        let eventData = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7);
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6);
          }
        }

        if (!eventType || !eventData) continue;

        try {
          const data = JSON.parse(eventData);
          handleSSEEvent(eventType, data);
        } catch {
          // JSON 解析失败，跳过
        }
      }
    }
  } catch (e) {
    console.error('SSE 对话失败:', e);
    // 更新最后的助手消息为错误状态
    const currentStore = useConversationStore.getState();
    const msgs = [...currentStore.messages];
    const last = msgs[msgs.length - 1];
    if (last && last.role === 'assistant' && last.streaming) {
      msgs[msgs.length - 1] = {
        ...last,
        content: last.content || '连接出了问题，请检查服务是否在运行。',
        streaming: false,
        metadata: { error: true },
      };
      currentStore.setMessages(msgs);
    }
  } finally {
    store.setSending(false);
    store.setStatusText(null);
  }
}

/** 处理单个 SSE 事件 */
function handleSSEEvent(type: string, data: Record<string, unknown>): void {
  const store = useConversationStore.getState();

  switch (type) {
    case 'status':
      store.setStatusText(data.text as string);
      break;

    case 'chunk':
      store.appendToLastAssistant(data.text as string);
      break;

    case 'result':
      store.finishStreaming({
        task_type: data.task_type as string,
        cost_usd: data.cost_usd as number,
        elapsed: data.elapsed as number,
        goal: data.goal as string,
      });
      break;

    case 'error':
      store.appendToLastAssistant(data.text as string);
      store.finishStreaming({ error: true });
      break;

    case 'done':
      store.setSending(false);
      store.setStatusText(null);
      break;
  }
}
