import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { StatusBreakdown } from '@/types';

interface StatusBreakdownChartProps {
  data: StatusBreakdown;
}

const STATUS_CONFIG = [
  { key: 'backlog', label: 'Backlog', color: '#71717a' },
  { key: 'inProgress', label: 'In Progress', color: '#3b82f6' },
  { key: 'codeReview', label: 'Code Review', color: '#8b5cf6' },
  { key: 'testing', label: 'Testing', color: '#f59e0b' },
  { key: 'done', label: 'Done', color: '#10b981' },
];

export function StatusBreakdownChart({ data }: StatusBreakdownChartProps) {
  const chartData = STATUS_CONFIG.map((status) => ({
    name: status.label,
    value: data[status.key as keyof StatusBreakdown],
    color: status.color,
  }));

  const total = Object.values(data).reduce((sum, val) => sum + val, 0);

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-[var(--color-text-muted)]">
          Status Breakdown
        </h3>
        <span className="text-xs text-[var(--color-text-muted)]">
          {total} total items
        </span>
      </div>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 0, right: 10, bottom: 0, left: 0 }}
          >
            <XAxis
              type="number"
              axisLine={false}
              tickLine={false}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
            />
            <YAxis
              type="category"
              dataKey="name"
              axisLine={false}
              tickLine={false}
              tick={{ fill: 'var(--color-text-secondary)', fontSize: 12, textAnchor: 'end' }}
              width={80}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--color-surface-elevated)',
                border: '1px solid var(--color-border)',
                borderRadius: '8px',
              }}
              labelStyle={{
                color: 'var(--color-text-primary)',
              }}
              itemStyle={{
                color: 'var(--color-text-secondary)',
              }}
              cursor={{ fill: 'var(--color-surface-elevated)', opacity: 0.5 }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-4 pt-4 border-t border-[var(--color-border)]">
        {chartData.map((item) => (
          <div key={item.name} className="flex items-center gap-2">
            <div
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="text-xs text-[var(--color-text-muted)]">
              {item.name}: {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
