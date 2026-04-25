import { create } from 'zustand';

/** 单条消息 */
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  /** 是否正在流式输出中 */
  streaming?: boolean;
  metadata?: {
    task_type?: string;
    cost_usd?: number;
    elapsed?: number;
    goal?: string;
    error?: boolean;
  };
}

/** 会话摘要（列表用） */
export interface SessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message: string;
}

/** 完整会话（含消息） */
export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

interface ConversationState {
  /** 会话列表 */
  sessions: SessionSummary[];
  /** 当前激活的会话 ID */
  activeSessionId: string | null;
  /** 当前会话的消息列表 */
  messages: Message[];
  /** 是否正在发送/等待响应 */
  sending: boolean;
  /** 当前状态提示文本（如"AI 正在思考..."） */
  statusText: string | null;
  /** 会话列表加载中 */
  loadingSessions: boolean;

  /* Actions */
  setSessions: (sessions: SessionSummary[]) => void;
  setActiveSession: (sessionId: string | null) => void;
  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;
  /** 更新最后一条助手消息（用于流式追加文本） */
  appendToLastAssistant: (chunk: string) => void;
  /** 标记最后一条助手消息流式结束 */
  finishStreaming: (metadata?: Message['metadata']) => void;
  setSending: (sending: boolean) => void;
  setStatusText: (text: string | null) => void;
  setLoadingSessions: (loading: boolean) => void;
  /** 清空当前会话状态 */
  clearActive: () => void;
}

export const useConversationStore = create<ConversationState>((set) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  sending: false,
  statusText: null,
  loadingSessions: false,

  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (sessionId) => set({ activeSessionId: sessionId }),
  setMessages: (messages) => set({ messages }),

  addMessage: (message) =>
    set((s) => ({ messages: [...s.messages, message] })),

  appendToLastAssistant: (chunk) =>
    set((s) => {
      const msgs = s.messages;
      if (msgs.length === 0) return s;
      const last = msgs[msgs.length - 1];
      if (last.role !== 'assistant' || !last.streaming) return s;
      // 用索引更新避免展开整个数组，减少流式输出时的 GC 压力
      const updated = [...msgs];
      updated[updated.length - 1] = { ...last, content: last.content + chunk };
      return { messages: updated };
    }),

  finishStreaming: (metadata) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = {
          ...last,
          streaming: false,
          metadata: { ...last.metadata, ...metadata },
        };
      }
      return { messages: msgs };
    }),

  setSending: (sending) => set({ sending }),
  setStatusText: (text) => set({ statusText: text }),
  setLoadingSessions: (loading) => set({ loadingSessions: loading }),

  clearActive: () =>
    set({ activeSessionId: null, messages: [], statusText: null, sending: false }),
}));
