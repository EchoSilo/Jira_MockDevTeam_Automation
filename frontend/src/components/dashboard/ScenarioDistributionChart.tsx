import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import type { ScenarioDistribution } from '@/types';

interface ScenarioDistributionChartProps {
  data: ScenarioDistribution;
}

const SCENARIO_CONFIG = [
  { key: 'normalFlow', label: 'Normal Flow', color: '#10b981' },
  { key: 'blocker', label: 'Blocker', color: '#ef4444' },
  { key: 'rework', label: 'Rework', color: '#f59e0b' },
  { key: 'scopeCreep', label: 'Scope Creep', color: '#8b5cf6' },
  { key: 'dependency', label: 'Dependency', color: '#3b82f6' },
];

export function ScenarioDistributionChart({
  data,
}: ScenarioDistributionChartProps) {
  const chartData = SCENARIO_CONFIG.map((scenario) => ({
    name: scenario.label,
    value: data[scenario.key as keyof ScenarioDistribution],
    color: scenario.color,
  })).filter((item) => item.value > 0);

  const total = Object.values(data).reduce((sum, val) => sum + val, 0);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-[var(--color-text-muted)]">
          Scenario Distribution
        </h3>
        <span className="text-xs text-[var(--color-text-muted)]">
          {total} active
        </span>
      </div>

      <div className="flex items-center gap-6">
        <div className="h-36 w-36">
          <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} debounce={50}>
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={35}
                outerRadius={55}
                paddingAngle={2}
                dataKey="value"
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-surface-elevated)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                  color: 'var(--color-text-primary)',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Legend */}
        <div className="flex flex-col gap-2">
          {SCENARIO_CONFIG.map((scenario) => {
            const value = data[scenario.key as keyof ScenarioDistribution];
            const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
            return (
              <div key={scenario.key} className="flex items-center gap-2">
                <div
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: scenario.color }}
                />
                <span className="text-xs text-[var(--color-text-secondary)]">
                  {scenario.label}
                </span>
                <span className="text-xs text-[var(--color-text-muted)] ml-auto">
                  {percentage}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
