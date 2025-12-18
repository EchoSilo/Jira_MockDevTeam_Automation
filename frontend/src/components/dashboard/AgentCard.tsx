import { User, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Agent } from '@/types';

interface AgentCardProps {
  agent: Agent;
}

const ROLE_COLORS: Record<string, string> = {
  pm: 'bg-purple-500/20 text-purple-400',
  developer: 'bg-blue-500/20 text-blue-400',
  qa: 'bg-amber-500/20 text-amber-400',
  tech_lead: 'bg-emerald-500/20 text-emerald-400',
};

const ROLE_LABELS: Record<string, string> = {
  pm: 'PM',
  developer: 'Dev',
  qa: 'QA',
  tech_lead: 'Lead',
};

export function AgentCard({ agent }: AgentCardProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg',
        'bg-[var(--color-surface-elevated)]',
        'border border-[var(--color-border)]',
        agent.isOverloaded && 'border-[var(--color-warning)]'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex h-10 w-10 items-center justify-center rounded-full',
          'bg-[var(--color-surface)]',
          'text-[var(--color-text-muted)]'
        )}
      >
        <User className="h-5 w-5" />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-[var(--color-text-primary)] truncate">
            {agent.name}
          </span>
          <span
            className={cn(
              'text-xs px-1.5 py-0.5 rounded',
              ROLE_COLORS[agent.role]
            )}
          >
            {ROLE_LABELS[agent.role]}
          </span>
        </div>
        <span className="text-xs text-[var(--color-text-muted)]">
          Team {agent.team.charAt(0).toUpperCase() + agent.team.slice(1)}
        </span>
      </div>

      {/* Ticket count */}
      <div className="flex items-center gap-2">
        {agent.isOverloaded && (
          <AlertTriangle className="h-4 w-4 text-[var(--color-warning)]" />
        )}
        <div className="flex flex-col items-end">
          <span
            className={cn(
              'text-lg font-semibold',
              agent.isOverloaded
                ? 'text-[var(--color-warning)]'
                : 'text-[var(--color-text-primary)]'
            )}
          >
            {agent.assignedTickets}
          </span>
          <span className="text-xs text-[var(--color-text-muted)]">tickets</span>
        </div>
      </div>
    </div>
  );
}
