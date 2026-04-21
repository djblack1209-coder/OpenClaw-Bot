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
  Bot, Brain, DollarSign, Dna, Globe,
  Layout, MessageSquare, Network, Settings, Shield,
  Zap, TrendingUp, Newspaper, Send,
} from 'lucide-react'

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
              👉 {t('commandPalette.execCommand')}: &quot;{inputValue.trim()}&quot;
            </CommandItem>
          </CommandGroup>
        )}

        <CommandGroup heading={t('commandPalette.navigation')}>
          <CommandItem onSelect={() => navigate('dashboard')}>
            <Layout className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.dashboard')}
          </CommandItem>
          <CommandItem onSelect={() => navigate('control')}>
            <Zap className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.control')}
          </CommandItem>
          <CommandItem onSelect={() => navigate('social')}>
            <Globe className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.social')}
          </CommandItem>
          <CommandItem onSelect={() => navigate('money')}>
            <DollarSign className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.money')}
          </CommandItem>
          <CommandItem onSelect={() => navigate('memory')}>
            <Brain className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.memory')}
          </CommandItem>
          <CommandItem onSelect={() => navigate('evolution')}>
            <Dna className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.evolution')}
          </CommandItem>
          <CommandItem onSelect={() => navigate('channels')}>
            <MessageSquare className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.channels')}
          </CommandItem>
          <CommandItem onSelect={() => navigate('gateway')}>
            <Network className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.gateway')}
          </CommandItem>
          <CommandItem onSelect={() => navigate('settings')}>
            <Settings className="mr-2 h-4 w-4" />
            {t('commandPalette.nav.settings')}
          </CommandItem>
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
