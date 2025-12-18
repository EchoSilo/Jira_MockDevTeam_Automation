import { cn } from '@/lib/utils';
import type { ReactNode } from 'react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  status?: 'default' | 'success' | 'warning' | 'error';
  compact?: boolean;
}

export function MetricCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  status = 'default',
  compact = false,
}: MetricCardProps) {
  const statusColors = {
    default: 'text-[var(--color-primary)]',
    success: 'text-[var(--color-success)]',
    warning: 'text-[var(--color-warning)]',
    error: 'text-[var(--color-error)]',
  };

  return (
    <div className={cn('card', compact && 'py-3 px-4')}>
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <span className={cn(
            'font-medium text-[var(--color-text-muted)]',
            compact ? 'text-xs' : 'text-sm'
          )}>
            {title}
          </span>
          <span className={cn(
            'font-semibold',
            compact ? 'text-lg' : 'text-2xl',
            statusColors[status]
          )}>
            {value}
          </span>
          {subtitle && (
            <span className={cn(
              'text-[var(--color-text-muted)]',
              compact ? 'text-xs' : 'text-xs'
            )}>
              {subtitle}
            </span>
          )}
        </div>

        {icon && !compact && (
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-lg',
              'bg-[var(--color-primary-muted)]',
              'text-[var(--color-primary)]'
            )}
          >
            {icon}
          </div>
        )}
      </div>

      {trend && !compact && (
        <div className="mt-3 flex items-center gap-1">
          <span
            className={cn(
              'text-xs font-medium',
              trend.isPositive
                ? 'text-[var(--color-success)]'
                : 'text-[var(--color-error)]'
            )}
          >
            {trend.isPositive ? '+' : ''}
            {trend.value}%
          </span>
          <span className="text-xs text-[var(--color-text-muted)]">
            vs last sprint
          </span>
        </div>
      )}
    </div>
  );
}
