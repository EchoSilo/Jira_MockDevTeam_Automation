import { Clock, AlertTriangle, XCircle, Play, GitBranch } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ActiveScenario } from '@/lib/api';

interface ScenarioTimelineProps {
  scenarios: ActiveScenario[];
}

const PHASE_COLORS: Record<string, string> = {
  backlog: 'bg-gray-500',
  assigned: 'bg-blue-500',
  in_progress: 'bg-blue-500',
  in_review: 'bg-purple-500',
  in_testing: 'bg-amber-500',
  blocked: 'bg-red-500',
  rejected: 'bg-red-400',
  fixing: 'bg-orange-500',
  completed: 'bg-green-500',
};

const SCENARIO_TYPE_ICONS: Record<string, React.ReactNode> = {
  normal_flow: <Play className="h-3 w-3" />,
  blocker: <AlertTriangle className="h-3 w-3" />,
  rework: <XCircle className="h-3 w-3" />,
  scope_creep: <GitBranch className="h-3 w-3" />,
  dependency: <Clock className="h-3 w-3" />,
};

function formatTimeAgo(timestamp: string): string {
  const now = new Date();
  const then = new Date(timestamp);
  const diffMs = now.getTime() - then.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 0) return `${diffDays}d ago`;
  if (diffHours > 0) return `${diffHours}h ago`;
  return 'Just now';
}

export function ScenarioTimeline({ scenarios }: ScenarioTimelineProps) {
  // Sort scenarios by start time (most recent first)
  const sortedScenarios = [...scenarios].sort((a, b) => {
    const aTime = a.started ? new Date(a.started).getTime() : 0;
    const bTime = b.started ? new Date(b.started).getTime() : 0;
    return bTime - aTime;
  });

  // Take top 8 most recent scenarios
  const recentScenarios = sortedScenarios.slice(0, 8);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-lg',
              'bg-[var(--color-primary-muted)]',
              'text-[var(--color-primary)]'
            )}
          >
            <Clock className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-muted)]">
              Scenario Timeline
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">
              LLM-driven ticket stories
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3 max-h-96 overflow-y-auto">
        {recentScenarios.map((scenario, index) => {
          const phaseColor = PHASE_COLORS[scenario.current_phase] || 'bg-gray-500';

          return (
            <div
              key={`${scenario.ticket_key}-${index}`}
              className={cn(
                'p-3 rounded-lg border',
                'bg-[var(--color-surface-elevated)]',
                'border-[var(--color-border)]',
                scenario.blocker_reason && 'border-l-4 border-l-red-500',
                scenario.rejection_reason && 'border-l-4 border-l-orange-500'
              )}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-medium text-[var(--color-primary)]">
                    {scenario.ticket_key}
                  </span>
                  <span
                    className={cn(
                      'text-xs px-1.5 py-0.5 rounded flex items-center gap-1',
                      scenario.scenario_type === 'blocker' && 'bg-red-500/20 text-red-400',
                      scenario.scenario_type === 'rework' && 'bg-orange-500/20 text-orange-400',
                      scenario.scenario_type === 'normal_flow' && 'bg-blue-500/20 text-blue-400',
                      scenario.scenario_type === 'scope_creep' && 'bg-purple-500/20 text-purple-400',
                      scenario.scenario_type === 'dependency' && 'bg-amber-500/20 text-amber-400'
                    )}
                  >
                    {SCENARIO_TYPE_ICONS[scenario.scenario_type]}
                    {scenario.scenario_type.replace('_', ' ')}
                  </span>
                </div>
                <span className={cn('text-xs px-2 py-0.5 rounded-full text-white', phaseColor)}>
                  {scenario.current_phase.replace('_', ' ')}
                </span>
              </div>

              {/* Blocker/Rejection reason */}
              {scenario.blocker_reason && (
                <div className="text-xs text-red-400 mb-2 flex items-start gap-1">
                  <AlertTriangle className="h-3 w-3 mt-0.5 flex-shrink-0" />
                  <span>{scenario.blocker_reason}</span>
                </div>
              )}
              {scenario.rejection_reason && (
                <div className="text-xs text-orange-400 mb-2 flex items-start gap-1">
                  <XCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
                  <span>{scenario.rejection_reason}</span>
                </div>
              )}

              {/* Assigned agent and started time */}
              <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                <div className="flex items-center gap-2">
                  {scenario.assigned_agent && (
                    <span className="font-medium">{scenario.assigned_agent}</span>
                  )}
                  {scenario.complexity && (
                    <span className="text-[var(--color-text-secondary)]">
                      ({scenario.complexity})
                    </span>
                  )}
                </div>
                {scenario.started && (
                  <span>{formatTimeAgo(scenario.started)}</span>
                )}
              </div>

              {/* Rejection count */}
              {scenario.times_rejected > 0 && (
                <div className="mt-2 text-xs text-orange-400">
                  {scenario.times_rejected} rejection{scenario.times_rejected > 1 ? 's' : ''}
                </div>
              )}
            </div>
          );
        })}

        {recentScenarios.length === 0 && (
          <div className="text-center py-8 text-[var(--color-text-muted)]">
            <Clock className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No active scenarios</p>
          </div>
        )}
      </div>
    </div>
  );
}
