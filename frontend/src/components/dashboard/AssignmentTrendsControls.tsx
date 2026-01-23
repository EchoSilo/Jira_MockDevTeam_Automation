import { cn } from '@/lib/utils';

type Granularity = 'daily' | 'weekly' | 'monthly';

interface AssignmentTrendsControlsProps {
  granularity: Granularity;
  onGranularityChange: (g: Granularity) => void;
  daysBack: number;
  onDaysBackChange: (days: number) => void;
}

const GRANULARITY_OPTIONS: { value: Granularity; label: string }[] = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
];

const DAYS_BACK_OPTIONS = [
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 30, label: '30 days' },
  { value: 60, label: '60 days' },
  { value: 90, label: '90 days' },
];

export function AssignmentTrendsControls({
  granularity,
  onGranularityChange,
  daysBack,
  onDaysBackChange,
}: AssignmentTrendsControlsProps) {
  return (
    <div className="flex items-center gap-4 mb-4">
      {/* Granularity selector - segmented button group */}
      <div className="flex rounded-lg overflow-hidden border border-[var(--color-border)]">
        {GRANULARITY_OPTIONS.map((option) => (
          <button
            key={option.value}
            onClick={() => onGranularityChange(option.value)}
            className={cn(
              'px-3 py-1.5 text-xs font-medium transition-colors',
              granularity === option.value
                ? 'bg-[var(--color-primary)] text-white'
                : 'bg-transparent text-[var(--color-text-muted)] hover:bg-[var(--color-surface-elevated)]'
            )}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Days back selector */}
      <select
        value={daysBack}
        onChange={(e) => onDaysBackChange(Number(e.target.value))}
        className={cn(
          'px-3 py-1.5 text-xs font-medium rounded-lg',
          'bg-[var(--color-surface)] border border-[var(--color-border)]',
          'text-[var(--color-text-primary)]',
          'focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]'
        )}
      >
        {DAYS_BACK_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            Last {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
