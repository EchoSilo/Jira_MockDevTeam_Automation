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
}

export function MetricCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  status = 'default',
}: MetricCardProps) {
  const statusColors = {
    default: 'text-[var(--color-primary)]',
    success: 'text-[var(--color-success)]',
    warning: 'text-[var(--color-warning)]',
    error: 'text-[var(--color-error)]',
  };

  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-[var(--color-text-muted)]">
            {title}
          </span>
          <span className={cn('text-2xl font-semibold', statusColors[status])}>
            {value}
          </span>
          {subtitle && (
            <span className="text-xs text-[var(--color-text-muted)]">
              {subtitle}
            </span>
          )}
        </div>

        {icon && (
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

      {trend && (
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
