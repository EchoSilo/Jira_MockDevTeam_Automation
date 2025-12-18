import { cn } from '@/lib/utils';

interface SprintOverviewCardProps {
  sprint: {
    name: string;
    day: number;
    totalDays: number;
  };
  completedItems: number;
  totalItems: number;
  progress: number;
  compact?: boolean;
}

export function SprintOverviewCard({
  sprint,
  completedItems,
  totalItems,
  progress,
  compact = false,
}: SprintOverviewCardProps) {
  const status =
    progress >= 80 ? 'success' :
    progress >= 50 ? 'default' :
    'warning';

  const statusColor = {
    success: 'text-[var(--color-success)]',
    warning: 'text-[var(--color-warning)]',
    default: 'text-[var(--color-primary)]',
  };

  const barColor = {
    success: 'bg-[var(--color-success)]',
    warning: 'bg-[var(--color-warning)]',
    default: 'bg-[var(--color-primary)]',
  };

  return (
    <div className={cn('card', compact && 'py-3 px-4')}>
      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium text-[var(--color-text-muted)]">
          {sprint.name}
        </span>

        <div className="flex items-baseline gap-2">
          <span className={cn(
            'font-semibold',
            compact ? 'text-lg' : 'text-2xl',
            statusColor[status]
          )}>
            {progress}%
          </span>
          <span className="text-xs text-[var(--color-text-muted)]">
            {completedItems}/{totalItems} items
          </span>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-[var(--color-surface-elevated)] rounded-full h-1.5 overflow-hidden">
          <div
            className={cn(
              'h-1.5 rounded-full transition-all duration-300',
              barColor[status]
            )}
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>

        <span className="text-xs text-[var(--color-text-muted)]">
          Day {sprint.day} of {sprint.totalDays}
        </span>
      </div>
    </div>
  );
}
