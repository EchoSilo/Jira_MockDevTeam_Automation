import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { useDashboardStore } from '@/store';
import { api } from '@/lib/api';
import type { Team } from '@/types';

// Fallback labels used until /api/teams responds (or if it fails). The `value`
// (internal key) is what drives all filtering; only the label is Jira-derived.
const DEFAULT_TEAMS: { value: Team; label: string }[] = [
  { value: 'all', label: 'All Teams' },
  { value: 'alpha', label: 'Alpha' },
  { value: 'beta', label: 'Beta' },
];

export function TeamFilter() {
  const { selectedTeam, setSelectedTeam } = useDashboardStore();
  const [teams, setTeams] = useState(DEFAULT_TEAMS);

  useEffect(() => {
    let active = true;
    api
      .getTeams()
      .then((res) => {
        if (!active) return;
        setTeams([
          { value: 'all', label: 'All Teams' },
          ...res.teams.map((t) => ({ value: t.key as Team, label: t.name })),
        ]);
      })
      .catch(() => {
        /* keep DEFAULT_TEAMS on failure */
      });
    return () => {
      active = false;
    };
  }, []);

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
      {teams.map((team) => (
        <button
          key={team.value}
          type="button"
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
