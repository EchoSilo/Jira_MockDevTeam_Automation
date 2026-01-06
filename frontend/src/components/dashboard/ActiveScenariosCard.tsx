import type { ScenarioDistribution, SprintScenario } from '@/types';

// Archetype display configuration
const ARCHETYPE_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  smooth_sprint: { label: 'Smooth Sprint', color: '#10b981', icon: '✓' },
  overloaded_sprint: { label: 'Overloaded Sprint', color: '#ef4444', icon: '⚠' },
  blocker_heavy: { label: 'Blocker-Heavy Sprint', color: '#f59e0b', icon: '🚧' },
  rework_sprint: { label: 'Rework Sprint', color: '#8b5cf6', icon: '🔄' },
  crunch_sprint: { label: 'Crunch Sprint', color: '#ec4899', icon: '🔥' },
  recovery_sprint: { label: 'Recovery Sprint', color: '#3b82f6', icon: '💚' },
};

// Legacy scenario config for backwards compatibility
const LEGACY_SCENARIO_CONFIG = [
  { key: 'normalFlow', label: 'Normal Flow', color: '#10b981' },
  { key: 'blocker', label: 'Blocker', color: '#ef4444' },
  { key: 'rework', label: 'Rework', color: '#f59e0b' },
  { key: 'scopeCreep', label: 'Scope Creep', color: '#8b5cf6' },
  { key: 'dependency', label: 'Dependency', color: '#3b82f6' },
];

interface ActiveScenariosCardProps {
  data: ScenarioDistribution;
  sprintScenario?: SprintScenario | null;
}

export function ActiveScenariosCard({ data, sprintScenario }: ActiveScenariosCardProps) {
  // If we have a sprint scenario, show the new format
  if (sprintScenario) {
    return <SprintScenarioView scenario={sprintScenario} />;
  }

  // Legacy view for backwards compatibility
  return <LegacyScenarioView data={data} />;
}

// New Sprint Scenario View
function SprintScenarioView({ scenario }: { scenario: SprintScenario }) {
  const archetypeConfig = ARCHETYPE_CONFIG[scenario.archetype] || {
    label: scenario.archetype_name,
    color: '#6b7280',
    icon: '',
  };

  const progressPercent = Math.round(scenario.actual_completion_rate * 100);
  const targetPercent = Math.round(scenario.target_completion_rate * 100);
  const eventsProgress = scenario.total_events > 0
    ? Math.round((scenario.events_executed / scenario.total_events) * 100)
    : 0;

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
          Sprint Scenario
        </h3>
        <div className="flex items-center gap-2">
          <span
            className="px-2 py-1 text-xs font-medium rounded-full text-white"
            style={{ backgroundColor: archetypeConfig.color }}
          >
            {archetypeConfig.icon} {archetypeConfig.label}
          </span>
        </div>
      </div>

      {/* Sprint info */}
      <div className="mb-4 p-3 bg-[var(--color-bg-secondary)] rounded-lg">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm text-[var(--color-text-muted)]">
            {scenario.sprint_name}
          </span>
          <span className="text-sm font-medium text-[var(--color-text-primary)]">
            Day {scenario.current_day} / {scenario.total_days}
          </span>
        </div>

        {/* Day progress bar */}
        <div className="h-2 bg-[var(--color-bg-tertiary)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${(scenario.current_day / scenario.total_days) * 100}%`,
              backgroundColor: archetypeConfig.color,
            }}
          />
        </div>
      </div>

      {/* Completion stats */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 bg-[var(--color-bg-secondary)] rounded-lg">
          <div className="text-xs text-[var(--color-text-muted)] mb-1">Items Progress</div>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-bold text-[var(--color-text-primary)]">
              {scenario.items_completed}
            </span>
            <span className="text-sm text-[var(--color-text-muted)]">
              / {scenario.total_items}
            </span>
          </div>
          <div className="text-xs mt-1">
            <span
              className={scenario.is_on_track ? 'text-green-500' : 'text-orange-500'}
            >
              {progressPercent}% done
            </span>
            <span className="text-[var(--color-text-muted)]">
              {' '}(target: {targetPercent}%)
            </span>
          </div>
        </div>

        <div className="p-3 bg-[var(--color-bg-secondary)] rounded-lg">
          <div className="text-xs text-[var(--color-text-muted)] mb-1">Script Progress</div>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-bold text-[var(--color-text-primary)]">
              {scenario.events_executed}
            </span>
            <span className="text-sm text-[var(--color-text-muted)]">
              / {scenario.total_events}
            </span>
          </div>
          <div className="text-xs text-[var(--color-text-muted)] mt-1">
            {eventsProgress}% events executed
          </div>
        </div>
      </div>

      {/* Status indicator */}
      <div className="flex items-center justify-between p-3 bg-[var(--color-bg-secondary)] rounded-lg">
        <div className="flex items-center gap-2">
          <div
            className={`w-3 h-3 rounded-full ${
              scenario.is_on_track ? 'bg-green-500' : 'bg-orange-500'
            }`}
          />
          <span className="text-sm text-[var(--color-text-primary)]">
            {scenario.is_on_track ? 'On Track' : 'Behind Schedule'}
          </span>
        </div>
        {scenario.current_mood && (
          <span className="text-xs text-[var(--color-text-muted)] capitalize">
            Mood: {scenario.current_mood.replace(/_/g, ' ')}
          </span>
        )}
      </div>

      {/* Today's events */}
      {scenario.today_events && scenario.today_events.length > 0 && (
        <div className="mt-4">
          <div className="text-xs text-[var(--color-text-muted)] mb-2">
            Today's Events ({scenario.today_events.filter(e => !e.executed).length} pending)
          </div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {scenario.today_events.map((event) => (
              <div
                key={event.event_id}
                className={`flex items-center gap-2 text-xs p-1.5 rounded ${
                  event.executed
                    ? 'bg-green-500/10 text-green-600'
                    : 'bg-[var(--color-bg-secondary)] text-[var(--color-text-secondary)]'
                }`}
              >
                <span>{event.executed ? '✓' : '○'}</span>
                <span className="font-medium">
                  {event.event_type.replace(/_/g, ' ')}
                </span>
                {event.ticket_key && (
                  <span className="text-[var(--color-text-muted)]">
                    ({event.ticket_key})
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Release context */}
      {scenario.release_context && (
        <div className="mt-3 pt-3 border-t border-[var(--color-border)]">
          <div className="text-xs text-[var(--color-text-muted)]">
            {scenario.release_context}
          </div>
        </div>
      )}
    </div>
  );
}

// Legacy Scenario View (backwards compatibility)
function LegacyScenarioView({ data }: { data: ScenarioDistribution }) {
  const scenarios = LEGACY_SCENARIO_CONFIG
    .map((scenario) => ({
      key: scenario.key,
      label: scenario.label,
      color: scenario.color,
      count: data[scenario.key as keyof ScenarioDistribution],
    }))
    .filter((item) => item.count > 0);

  const total = Object.values(data).reduce((sum, val) => sum + val, 0);
  const percentage = (count: number) => {
    return total > 0 ? Math.round((count / total) * 100) : 0;
  };

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
          Active Scenarios
        </h3>
        <span className="text-2xl font-bold text-[var(--color-primary)]">
          {total}
        </span>
      </div>

      {scenarios.length > 0 ? (
        <div className="space-y-3 max-h-80 overflow-y-auto">
          {scenarios.map((scenario) => (
            <div key={scenario.key} className="flex items-center gap-3">
              <div
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: scenario.color }}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[var(--color-text-primary)]">
                  {scenario.label}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {scenario.count} items ({percentage(scenario.count)}%)
                </p>
              </div>
              <span className="text-sm font-semibold text-[var(--color-text-secondary)]">
                {scenario.count}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-6">
          <p className="text-sm text-[var(--color-text-muted)]">
            No active scenarios
          </p>
        </div>
      )}
    </div>
  );
}
