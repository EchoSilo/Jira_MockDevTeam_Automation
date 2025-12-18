import { User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/store';

const PMS = [
  { id: 'alpha_pm' as const, name: 'Sarah Chen', team: 'Alpha' },
  { id: 'beta_pm' as const, name: 'David Kim', team: 'Beta' },
];

export function PMSelector() {
  const { selectedPmId, setSelectedPmId } = useChatStore();

  return (
    <div className="flex items-center gap-2 p-1 bg-[var(--color-surface)] rounded-lg border border-[var(--color-border)]">
      {PMS.map((pm) => (
        <button
          key={pm.id}
          onClick={() => setSelectedPmId(pm.id)}
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-md transition-all duration-200',
            selectedPmId === pm.id
              ? 'bg-[var(--color-primary)] text-white'
              : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-elevated)]'
          )}
        >
          <div
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded-full',
              selectedPmId === pm.id
                ? 'bg-white/20'
                : 'bg-[var(--color-surface-elevated)]'
            )}
          >
            <User className="h-3.5 w-3.5" />
          </div>
          <div className="text-left">
            <div className="text-sm font-medium">{pm.name}</div>
            <div
              className={cn(
                'text-xs',
                selectedPmId === pm.id
                  ? 'text-white/70'
                  : 'text-[var(--color-text-muted)]'
              )}
            >
              Team {pm.team}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
