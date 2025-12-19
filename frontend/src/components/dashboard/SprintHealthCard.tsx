import { cn } from '@/lib/utils';

interface SprintHealthCardProps {
  progress: number;
  currentDay: number;
  totalDays: number;
  compact?: boolean;
}

export function SprintHealthCard({
  progress,
  currentDay,
  totalDays,
  compact = false,
}: SprintHealthCardProps) {
  const expectedProgress = (currentDay / totalDays) * 100;
  const delta = progress - expectedProgress;

  let health: 'good' | 'at-risk' | 'behind';
  let status: 'success' | 'warning' | 'error';

  if (delta >= -10) {
    health = 'good';
    status = 'success';
  } else if (delta >= -20) {
    health = 'at-risk';
    status = 'warning';
  } else {
    health = 'behind';
    status = 'error';
  }

  const healthLabels = {
    good: 'Good',
    'at-risk': 'At Risk',
    behind: 'Behind',
  };

  const statusColor = {
    success: 'text-[var(--color-success)]',
    warning: 'text-[var(--color-warning)]',
    error: 'text-[var(--color-error)]',
  };

  return (
    <div className={cn('card', compact && 'py-3 px-4')}>
      <div className="flex flex-col gap-1">
        <span className={cn(
          'font-medium text-[var(--color-text-muted)]',
          compact ? 'text-xs' : 'text-sm'
        )}>
          Sprint Health
        </span>

        <span className={cn(
          'font-bold',
          compact ? 'text-2xl' : 'text-3xl',
          statusColor[status]
        )}>
          {healthLabels[health]}
        </span>

        {delta < -10 && (
          <span className="text-xs text-[var(--color-text-muted)]">
            {Math.abs(delta).toFixed(0)}% behind
          </span>
        )}
      </div>
    </div>
  );
}
