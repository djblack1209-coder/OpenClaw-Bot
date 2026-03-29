import { useState, useEffect } from 'react'
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
  Layout, MessageSquare, Settings, Shield,
  Zap, TrendingUp, Newspaper,
} from 'lucide-react'

export function CommandPalette() {
  const [open, setOpen] = useState(false)
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

  const navigate = (page: string) => {
    setCurrentPage(page as PageType)
    setOpen(false)
  }

  const runAction = async (label: string, action: () => Promise<unknown>) => {
    setOpen(false)
    toast.promise(action(), {
      loading: `${label}...`,
      success: `${label} 完成`,
      error: (e: unknown) => `${label} 失败: ${e instanceof Error ? e.message : String(e)}`,
    })
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="输入命令或搜索... (Ctrl+K)" />
      <CommandList>
        <CommandEmpty>没有找到匹配的命令</CommandEmpty>

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
          <CommandItem onSelect={() => navigate('settings')}>
            <Settings className="mr-2 h-4 w-4" />
            设置
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="快捷操作">
          <CommandItem onSelect={() => runAction('热点扫描', () => api.clawbotSocialTopics(10))}>
            <Newspaper className="mr-2 h-4 w-4" />
            热点扫描
          </CommandItem>
          <CommandItem onSelect={() => runAction('进化扫描', () => api.clawbotEvolutionScan())}>
            <Dna className="mr-2 h-4 w-4" />
            进化扫描 (GitHub Trending)
          </CommandItem>
          <CommandItem onSelect={() => runAction('系统状态', () => api.clawbotStatus())}>
            <Shield className="mr-2 h-4 w-4" />
            检查系统状态
          </CommandItem>
          <CommandItem onSelect={() => runAction('交易系统', () => api.clawbotTradingSystem())}>
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
