import { Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AgentCard } from './AgentCard';
import type { Agent } from '@/types';

interface WorkloadCardProps {
  agents: Agent[];
}

export function WorkloadCard({ agents }: WorkloadCardProps) {
  const overloadedCount = agents.filter((a) => a.isOverloaded).length;
  const totalTickets = agents.reduce((sum, a) => sum + a.assignedTickets, 0);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-lg',
              'bg-[var(--color-info-muted)]',
              'text-[var(--color-info)]'
            )}
          >
            <Users className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-muted)]">
              Team Workload
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">
              {totalTickets} tickets across {agents.length} members
            </p>
          </div>
        </div>

        {overloadedCount > 0 && (
          <span
            className={cn(
              'text-xs px-2 py-1 rounded-full',
              'bg-[var(--color-warning-muted)]',
              'text-[var(--color-warning)]'
            )}
          >
            {overloadedCount} overloaded
          </span>
        )}
      </div>

      <div className="space-y-2 max-h-72 overflow-y-auto">
        {[...agents]
          .sort((a, b) => b.assignedTickets - a.assignedTickets)
          .map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
      </div>
    </div>
  );
}
