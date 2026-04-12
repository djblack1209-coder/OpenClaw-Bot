import { useState, useEffect, useCallback } from 'react'
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
} from '@/components/ui/command'
import { api } from '@/lib/tauri'
import { useAppStore } from '@/stores/appStore'
import type { PageType } from '@/App'
import { toast } from 'sonner'

import {
  Bot, Brain, DollarSign, Dna, Globe,
  Layout, MessageSquare, Network, Settings, Shield,
  Zap, TrendingUp, Newspaper, Send,
} from 'lucide-react'

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const setCurrentPage = useAppStore((s) => s.setCurrentPage)

  // Ctrl+K / Cmd+K 切换命令面板
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    document.addEventListener('keydown', down)
    return () => document.removeEventListener('keydown', down)
  }, [])

  // 面板关闭时清空输入
  useEffect(() => {
    if (!open) {
      setInputValue('')
    }
  }, [open])

  const navigate = (page: string) => {
    setCurrentPage(page as PageType)
    setOpen(false)
  }

  const runAction = async (label: string, action: () => Promise<unknown>, formatResult?: (data: unknown) => string) => {
    setOpen(false)
    try {
      const result = await action()
      const detail = formatResult ? formatResult(result) : ''
      toast.success(`${label} 完成`, { description: detail || undefined })
    } catch (e: unknown) {
      toast.error(`${label} 失败`, { description: e instanceof Error ? e.message : String(e) })
    }
  }

  // 将用户输入作为自然语言指令发送给 OMEGA Brain
  const executeCommand = useCallback((command: string) => {
    if (!command.trim()) return
    const trimmed = command.trim()
    setOpen(false)
    toast.promise(api.omegaProcess(trimmed), {
      loading: `正在执行指令: "${trimmed}"`,
      success: `指令已发送: ${trimmed}`,
      error: (e: unknown) => `指令执行失败: ${e instanceof Error ? e.message : String(e)}`,
    })
  }, [])

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="输入命令或搜索... (Ctrl+K)"
        value={inputValue}
        onValueChange={setInputValue}
      />
      <CommandList>
        <CommandEmpty>没有找到匹配的命令</CommandEmpty>

        {/* 动态执行：用户输入任意文本时，显示"执行指令"选项 */}
        {inputValue.trim().length > 0 && (
          <CommandGroup heading="动态执行">
            <CommandItem
              onSelect={() => executeCommand(inputValue)}
              value={`__execute__${inputValue}`}
              forceMount
            >
              <Send className="mr-2 h-4 w-4" />
              👉 执行指令: &quot;{inputValue.trim()}&quot;
            </CommandItem>
          </CommandGroup>
        )}

        <CommandGroup heading="导航">
          <CommandItem onSelect={() => navigate('dashboard')}>
            <Layout className="mr-2 h-4 w-4" />
            概览
          </CommandItem>
          <CommandItem onSelect={() => navigate('control')}>
            <Zap className="mr-2 h-4 w-4" />
            总控中心
          </CommandItem>
          <CommandItem onSelect={() => navigate('social')}>
            <Globe className="mr-2 h-4 w-4" />
            社媒总控
          </CommandItem>
          <CommandItem onSelect={() => navigate('money')}>
            <DollarSign className="mr-2 h-4 w-4" />
            盈利总控
          </CommandItem>
          <CommandItem onSelect={() => navigate('memory')}>
            <Brain className="mr-2 h-4 w-4" />
            记忆脑图
          </CommandItem>
          <CommandItem onSelect={() => navigate('evolution')}>
            <Dna className="mr-2 h-4 w-4" />
            进化引擎
          </CommandItem>
          <CommandItem onSelect={() => navigate('channels')}>
            <MessageSquare className="mr-2 h-4 w-4" />
            消息渠道
          </CommandItem>
          <CommandItem onSelect={() => navigate('gateway')}>
            <Network className="mr-2 h-4 w-4" />
            API 网关
          </CommandItem>
          <CommandItem onSelect={() => navigate('settings')}>
            <Settings className="mr-2 h-4 w-4" />
            设置
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="快捷操作">
          <CommandItem onSelect={() => runAction('热点扫描', () => api.clawbotSocialTopics(10), (d: unknown) => {
            const data = d as Record<string, unknown> | undefined;
            const topics = (data?.topics ?? data?.data) as unknown[] | undefined;
            return topics?.length ? `发现 ${topics.length} 条热点` : '扫描完成';
          })}>
            <Newspaper className="mr-2 h-4 w-4" />
            热点扫描
          </CommandItem>
          <CommandItem onSelect={() => runAction('进化扫描', () => api.clawbotEvolutionScan(), (d: unknown) => {
            const data = d as Record<string, unknown> | undefined;
            return String(data?.message ?? data?.status ?? '扫描已提交');
          })}>
            <Dna className="mr-2 h-4 w-4" />
            进化扫描 (GitHub Trending)
          </CommandItem>
          <CommandItem onSelect={() => runAction('系统状态', () => api.clawbotStatus(), (d: unknown) => {
            const data = d as Record<string, unknown> | undefined;
            const s = data?.status ?? data?.state;
            return s ? `状态: ${s}` : '系统运行中';
          })}>
            <Shield className="mr-2 h-4 w-4" />
            检查系统状态
          </CommandItem>
          <CommandItem onSelect={() => runAction('交易系统', () => api.clawbotTradingSystem(), (d: unknown) => {
            const data = d as Record<string, unknown> | undefined;
            const s = data?.status ?? data?.state;
            return s ? `交易系统: ${s}` : '查询完成';
          })}>
            <TrendingUp className="mr-2 h-4 w-4" />
            交易系统状态
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="服务管理">
          <CommandItem onSelect={() => runAction('启动自动驾驶', () => api.clawbotAutopilotStart())}>
            <Bot className="mr-2 h-4 w-4" />
            启动社交自动驾驶
          </CommandItem>
          <CommandItem onSelect={() => runAction('停止自动驾驶', () => api.clawbotAutopilotStop())}>
            <Bot className="mr-2 h-4 w-4" />
            停止社交自动驾驶
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
