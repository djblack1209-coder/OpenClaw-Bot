/**
 * Skeleton — 通用骨架屏加载组件集合
 * 提供基础骨架块和常见布局组合（统计卡片、表格行、列表等）
 */

interface SkeletonProps {
  /** 额外的 CSS 类名，用于控制尺寸 */
  className?: string;
}

/** 基础骨架块 — 通过 className 控制宽高 */
export function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div className={`animate-pulse bg-muted rounded ${className}`} />
  );
}

/** 统计卡片骨架 */
export function StatCardSkeleton() {
  return (
    <div className="p-4 rounded-lg border bg-card">
      <Skeleton className="h-4 w-20 mb-2" />
      <Skeleton className="h-8 w-32" />
    </div>
  );
}

/** 表格行骨架 */
export function TableRowSkeleton({ cols = 4 }: { cols?: number }) {
  return (
    <tr className="border-b">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="p-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  );
}

/** 表格骨架（多行） */
export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <TableRowSkeleton key={i} cols={cols} />
      ))}
    </>
  );
}

/** 卡片网格骨架 */
export function CardGridSkeleton({ cards = 6 }: { cards?: number }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {Array.from({ length: cards }).map((_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </div>
  );
}

/** 列表骨架 */
export function ListSkeleton({ items = 5 }: { items?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 p-3">
          <Skeleton className="h-8 w-8 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}
