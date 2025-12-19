import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { VelocityDataPoint } from '@/types';

interface VelocityChartProps {
  data: VelocityDataPoint[];
}

export function VelocityChart({ data }: VelocityChartProps) {
  const chartData = data.map((d) => ({
    name: `Sprint ${d.sprintNumber}`,
    value: d.completedItems,
  }));

  // Calculate trend
  const lastTwo = data.slice(-2);
  let trend = 0;
  if (lastTwo.length === 2 && lastTwo[0].completedItems > 0) {
    trend = Math.round(
      ((lastTwo[1].completedItems - lastTwo[0].completedItems) /
        lastTwo[0].completedItems) *
        100
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-lg',
              'bg-[var(--color-success-muted)]',
              'text-[var(--color-success)]'
            )}
          >
            <TrendingUp className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-muted)]">
              Velocity Trend
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">
              Items completed per sprint
            </p>
          </div>
        </div>

        {trend !== 0 && (
          <span
            className={cn(
              'text-xs px-2 py-1 rounded-full',
              trend > 0
                ? 'bg-[var(--color-success-muted)] text-[var(--color-success)]'
                : 'bg-[var(--color-error-muted)] text-[var(--color-error)]'
            )}
          >
            {trend > 0 ? '+' : ''}
            {trend}%
          </span>
        )}
      </div>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--color-border)"
              vertical={false}
            />
            <XAxis
              dataKey="name"
              axisLine={false}
              tickLine={false}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 12 }}
              width={30}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--color-surface-elevated)',
                border: '1px solid var(--color-border)',
                borderRadius: '8px',
                color: 'var(--color-text-primary)',
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--color-primary)"
              strokeWidth={2}
              dot={{ fill: 'var(--color-primary)', strokeWidth: 0, r: 4 }}
              activeDot={{ r: 6, fill: 'var(--color-primary-hover)' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
