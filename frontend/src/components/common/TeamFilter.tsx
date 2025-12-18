import { cn } from '@/lib/utils';
import { useDashboardStore } from '@/store';
import type { Team } from '@/types';

const TEAMS: { value: Team; label: string }[] = [
  { value: 'all', label: 'All Teams' },
  { value: 'alpha', label: 'Alpha' },
  { value: 'beta', label: 'Beta' },
];

export function TeamFilter() {
  const { selectedTeam, setSelectedTeam } = useDashboardStore();

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1 rounded-lg p-1',
        'bg-[var(--color-surface)]',
        'border border-[var(--color-border)]'
      )}
      role="tablist"
      aria-label="Filter by team"
    >
      {TEAMS.map((team) => (
        <button
          key={team.value}
          role="tab"
          aria-selected={selectedTeam === team.value}
          onClick={() => setSelectedTeam(team.value)}
          className={cn(
            'px-3 py-1.5 text-sm font-medium rounded-md transition-all duration-200',
            selectedTeam === team.value
              ? 'bg-[var(--color-primary)] text-white'
              : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-elevated)]'
          )}
        >
          {team.label}
        </button>
      ))}
    </div>
  );
}
