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
import { toast } from '@/lib/notify'
import { useLanguage } from '@/i18n'

import {
  Bot, Brain, DollarSign, Dna, Fish, Globe,
  Home, Landmark, Layout, MessageSquare, Network, Settings, Shield,
  ShoppingBag, Zap, TrendingUp, Newspaper, Send,
} from 'lucide-react'

const mainNavigationItems: Array<{ page: PageType; labelKey: string; icon: React.ElementType }> = [
  { page: 'home', labelKey: 'sidebar.home', icon: Home },
  { page: 'assistant', labelKey: 'sidebar.assistant', icon: MessageSquare },
  { page: 'worldmonitor', labelKey: 'sidebar.worldmonitor', icon: Globe },
  { page: 'newsfeed', labelKey: 'sidebar.newsfeed', icon: Newspaper },
  { page: 'finradar', labelKey: 'sidebar.finradar', icon: Landmark },
  { page: 'portfolio', labelKey: 'sidebar.portfolio', icon: TrendingUp },
  { page: 'bots', labelKey: 'sidebar.bots', icon: Bot },
  { page: 'store', labelKey: 'sidebar.store', icon: ShoppingBag },
  { page: 'xianyu', labelKey: 'sidebar.xianyu', icon: Fish },
  { page: 'social', labelKey: 'sidebar.social', icon: Globe },
  { page: 'settings', labelKey: 'sidebar.settings', icon: Settings },
]

const developerNavigationItems: Array<{ page: PageType; labelKey: string; icon: React.ElementType }> = [
  { page: 'dashboard', labelKey: 'commandPalette.nav.dashboard', icon: Layout },
  { page: 'control', labelKey: 'commandPalette.nav.control', icon: Zap },
  { page: 'money', labelKey: 'commandPalette.nav.money', icon: DollarSign },
  { page: 'memory', labelKey: 'commandPalette.nav.memory', icon: Brain },
  { page: 'evolution', labelKey: 'commandPalette.nav.evolution', icon: Dna },
  { page: 'channels', labelKey: 'commandPalette.nav.channels', icon: MessageSquare },
  { page: 'gateway', labelKey: 'commandPalette.nav.gateway', icon: Network },
]

export function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const setCurrentPage = useAppStore((s) => s.setCurrentPage)
  const { t } = useLanguage()

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
      toast.success(`${label} ${t('commandPalette.actionDone')}`, { description: detail || undefined, channel: 'log' })
    } catch (e: unknown) {
      toast.error(`${label} ${t('commandPalette.actionFailed')}`, { description: e instanceof Error ? e.message : String(e), channel: 'notification' })
    }
  }

  // 将用户输入作为自然语言指令发送给 OMEGA Brain
  const executeCommand = useCallback((command: string) => {
    if (!command.trim()) return
    const trimmed = command.trim()
    setOpen(false)
    toast.promise(api.omegaProcess(trimmed), {
      loading: `${t('commandPalette.executing')}: "${trimmed}"`,
      success: `${t('commandPalette.commandSent')}: ${trimmed}`,
      error: (e: unknown) => `${t('commandPalette.commandFailed')}: ${e instanceof Error ? e.message : String(e)}`,
    })
  }, [])

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder={t('commandPalette.placeholder')}
        value={inputValue}
        onValueChange={setInputValue}
      />
      <CommandList>
        <CommandEmpty>{t('commandPalette.noResults')}</CommandEmpty>

        {/* 动态执行：用户输入任意文本时，显示"执行指令"选项 */}
        {inputValue.trim().length > 0 && (
          <CommandGroup heading={t('commandPalette.dynamicExec')}>
            <CommandItem
              onSelect={() => executeCommand(inputValue)}
              value={`__execute__${inputValue}`}
              forceMount
            >
              <Send className="mr-2 h-4 w-4" />
              {t('commandPalette.execCommand')}: &quot;{inputValue.trim()}&quot;
            </CommandItem>
          </CommandGroup>
        )}

        <CommandGroup heading={t('commandPalette.navigation')}>
          {mainNavigationItems.map(({ page, labelKey, icon: Icon }) => (
            <CommandItem key={page} onSelect={() => navigate(page)}>
              <Icon className="mr-2 h-4 w-4" />
              {t(labelKey)}
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandGroup heading={t('sidebar.devTools')}>
          {developerNavigationItems.map(({ page, labelKey, icon: Icon }) => (
            <CommandItem key={page} onSelect={() => navigate(page)}>
              <Icon className="mr-2 h-4 w-4" />
              {t(labelKey)}
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading={t('commandPalette.quickActions')}>
          <CommandItem onSelect={() => runAction(t('commandPalette.action.hotScan'), () => api.clawbotSocialTopics(10), (d: unknown) => {
            const data = d as Record<string, unknown> | undefined;
            const topics = (data?.topics ?? data?.data) as unknown[] | undefined;
            return topics?.length ? `${t('commandPalette.action.foundTopics').replace('{n}', String(topics.length))}` : t('commandPalette.action.scanDone');
          })}>
            <Newspaper className="mr-2 h-4 w-4" />
            {t('commandPalette.action.hotScan')}
          </CommandItem>
          <CommandItem onSelect={() => runAction(t('commandPalette.action.evolutionScan'), () => api.clawbotEvolutionScan(), (d: unknown) => {
            const data = d as Record<string, unknown> | undefined;
            return String(data?.message ?? data?.status ?? t('commandPalette.action.scanSubmitted'));
          })}>
            <Dna className="mr-2 h-4 w-4" />
            {t('commandPalette.action.evolutionScan')}
          </CommandItem>
          <CommandItem onSelect={() => runAction(t('commandPalette.action.systemStatus'), () => api.clawbotStatus(), (d: unknown) => {
            const data = d as Record<string, unknown> | undefined;
            const s = data?.status ?? data?.state;
            return s ? `${t('commandPalette.action.statusLabel')}: ${s}` : t('commandPalette.action.systemRunning');
          })}>
            <Shield className="mr-2 h-4 w-4" />
            {t('commandPalette.action.checkStatus')}
          </CommandItem>
          <CommandItem onSelect={() => runAction(t('commandPalette.action.tradingSystem'), () => api.clawbotTradingSystem(), (d: unknown) => {
            const data = d as Record<string, unknown> | undefined;
            const s = data?.status ?? data?.state;
            return s ? `${t('commandPalette.action.tradingSystemLabel')}: ${s}` : t('commandPalette.action.queryDone');
          })}>
            <TrendingUp className="mr-2 h-4 w-4" />
            {t('commandPalette.action.tradingStatus')}
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading={t('commandPalette.serviceManagement')}>
          <CommandItem onSelect={() => runAction(t('commandPalette.action.startAutopilot'), () => api.clawbotAutopilotStart())}>
            <Bot className="mr-2 h-4 w-4" />
            {t('commandPalette.action.startSocialAutopilot')}
          </CommandItem>
          <CommandItem onSelect={() => runAction(t('commandPalette.action.stopAutopilot'), () => api.clawbotAutopilotStop())}>
            <Bot className="mr-2 h-4 w-4" />
            {t('commandPalette.action.stopSocialAutopilot')}
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
