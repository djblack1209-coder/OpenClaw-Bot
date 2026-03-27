import { Skeleton } from '@/components/ui/skeleton'
import { Bot } from 'lucide-react'

interface OfflineGuideProps {
  title?: string
  description?: string
  action?: { label: string; onClick: () => void }
  showSkeleton?: boolean
}

/**
 * Contextual offline state — tells users WHAT TO DO, not just "offline".
 * Drop this into any page that depends on ClawBot API connectivity.
 */
export function OfflineGuide({ title, description, action, showSkeleton }: OfflineGuideProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      {/* Icon */}
      <div className="w-16 h-16 rounded-full bg-dark-700 flex items-center justify-center mb-4">
        <Bot className="h-8 w-8 text-gray-500" />
      </div>
      <h3 className="text-lg font-semibold text-gray-300 mb-2">
        {title || 'ClawBot 未连接'}
      </h3>
      <p className="text-sm text-gray-500 max-w-md mb-4">
        {description || '请确保 ClawBot Python 后端正在运行。在控制中心启动服务后，数据将自动加载。'}
      </p>
      {action && (
        <button
          onClick={action.onClick}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm transition-colors"
        >
          {action.label}
        </button>
      )}
      {showSkeleton && (
        <div className="w-full max-w-lg mt-6 space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-12 w-3/4" />
        </div>
      )}
    </div>
  )
}
