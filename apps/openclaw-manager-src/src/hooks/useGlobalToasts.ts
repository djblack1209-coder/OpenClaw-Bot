import { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { CLAWBOT_WS_URL } from '@/lib/tauri'

/**
 * Global toast hook — subscribes to ClawBot WebSocket events
 * and shows real-time toasts for important events.
 *
 * Mounted once in App.tsx.
 */
export function useGlobalToasts() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    let delay = 1000

    function connect() {
      try {
        const ws = new WebSocket(CLAWBOT_WS_URL)
        wsRef.current = ws

        ws.onopen = () => {
          delay = 1000
          // 连接时不弹 toast — 太频繁
        }

        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data)
            handleEvent(msg)
          } catch {
            // 格式异常的消息 — 忽略
          }
        }

        ws.onclose = () => {
          reconnectTimer.current = setTimeout(connect, delay)
          delay = Math.min(delay * 2, 30000)
        }
      } catch {
        // 连接失败 — 通过 onclose 自动重试
      }
    }

    function handleEvent(msg: unknown) {
      const parsed = msg as { type?: string; data?: Record<string, unknown> };
      const type = parsed.type
      const data = parsed.data || {} as Record<string, unknown>
      const message = String(data.message || data.msg || '')

      switch (type) {
        case 'trade_executed':
          toast.success('交易执行', { description: message })
          break
        case 'trade_signal':
          toast.info('交易信号', { description: message })
          break
        case 'risk_alert':
          toast.warning('风控告警', { description: message })
          break
        case 'bot_error':
          toast.error('Bot 异常', { description: message })
          break
        case 'social_published':
          toast.success('社交发布', { description: message })
          break
        case 'autopilot_event':
          toast('自动驾驶', { description: message })
          break
        case 'heartbeat':
          // 静默 — 心跳不触发 toast
          break
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])
}
