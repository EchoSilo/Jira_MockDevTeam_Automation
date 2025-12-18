import type { ScenarioDistribution } from '@/types';

const SCENARIO_CONFIG = [
  { key: 'normalFlow', label: 'Normal Flow', color: '#10b981' },
  { key: 'blocker', label: 'Blocker', color: '#ef4444' },
  { key: 'rework', label: 'Rework', color: '#f59e0b' },
  { key: 'scopeCreep', label: 'Scope Creep', color: '#8b5cf6' },
  { key: 'dependency', label: 'Dependency', color: '#3b82f6' },
];

interface ActiveScenariosCardProps {
  data: ScenarioDistribution;
}

export function ActiveScenariosCard({ data }: ActiveScenariosCardProps) {
  const scenarios = SCENARIO_CONFIG
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
