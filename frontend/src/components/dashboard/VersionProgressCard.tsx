import { BarChart3 } from 'lucide-react';
import type { VersionProgress } from '@/lib/api';

interface VersionProgressCardProps {
  versionName: string | null;
  progress: VersionProgress | null;
  isLoading?: boolean;
}

export function VersionProgressCard({
  versionName,
  progress,
  isLoading,
}: VersionProgressCardProps) {
  if (!versionName) {
    return (
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              Version Progress
            </h3>
          </div>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">
          Select a version to view progress
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="card">
        <div className="h-40 bg-[var(--color-surface-elevated)] rounded animate-pulse" />
      </div>
    );
  }

  if (!progress) {
    return (
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-success-muted)] text-[var(--color-success)]">
            <BarChart3 className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              {versionName}
            </h3>
          </div>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">
          No issues assigned to this version
        </p>
      </div>
    );
  }

  const segments = [
    {
      label: 'Done',
      value: progress.done,
      percent: progress.done_percent,
      color: '#10b981',
    },
    {
      label: 'In Progress',
      value: progress.in_progress,
      percent: progress.in_progress_percent,
      color: '#3b82f6',
    },
    {
      label: 'To Do',
      value: progress.todo,
      percent: Math.max(0, 100 - progress.done_percent - progress.in_progress_percent),
      color: '#71717a',
    },
  ];

  return (
    <div className="card">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-success-muted)] text-[var(--color-success)]">
          <BarChart3 className="h-5 w-5" />
        </div>
        <div>
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
            {versionName} Progress
          </h3>
          <p className="text-xs text-[var(--color-text-muted)]">
            {progress.done}/{progress.total} completed
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-4 rounded-full overflow-hidden bg-[var(--color-surface-elevated)] flex mb-4">
        {segments.map(
          segment =>
            segment.percent > 0 && (
              <div
                key={segment.label}
                className="h-full transition-all"
                style={{
                  width: `${segment.percent}%`,
                  backgroundColor: segment.color,
                }}
              />
            )
        )}
      </div>

      {/* Legend */}
      <div className="grid grid-cols-3 gap-4">
        {segments.map(segment => (
          <div key={segment.label} className="text-center">
            <p className="text-2xl font-bold" style={{ color: segment.color }}>
              {segment.value}
            </p>
            <p className="text-xs text-[var(--color-text-muted)]">{segment.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
