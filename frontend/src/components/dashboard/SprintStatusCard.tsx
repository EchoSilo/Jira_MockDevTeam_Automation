import { Calendar, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Sprint } from '@/types';

interface SprintStatusCardProps {
  sprint: Sprint;
}

export function SprintStatusCard({ sprint }: SprintStatusCardProps) {
  const progress = (sprint.day / sprint.totalDays) * 100;
  const daysRemaining = sprint.totalDays - sprint.day;

  return (
    <div className="card">
      <div className="flex items-start justify-between mb-4">
        <div>
          <span className="text-sm font-medium text-[var(--color-text-muted)]">
            Current Sprint
          </span>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
            {sprint.name}
          </h3>
        </div>
        <div
          className={cn(
            'flex h-10 w-10 items-center justify-center rounded-lg',
            'bg-[var(--color-primary-muted)]',
            'text-[var(--color-primary)]'
          )}
        >
          <Calendar className="h-5 w-5" />
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs mb-2">
          <span className="text-[var(--color-text-muted)]">Progress</span>
          <span className="text-[var(--color-text-secondary)]">
            Day {sprint.day} of {sprint.totalDays}
          </span>
        </div>
        <div className="h-2 bg-[var(--color-surface-elevated)] rounded-full overflow-hidden">
          <div
            className="h-full bg-[var(--color-primary)] rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Days remaining */}
      <div className="flex items-center gap-2 text-sm">
        <Clock className="h-4 w-4 text-[var(--color-text-muted)]" />
        <span className="text-[var(--color-text-secondary)]">
          {daysRemaining} {daysRemaining === 1 ? 'day' : 'days'} remaining
        </span>
      </div>
    </div>
  );
}
