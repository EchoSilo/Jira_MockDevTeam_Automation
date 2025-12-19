import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from 'recharts';
import { Target } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { BurndownDataPoint } from '@/types';

interface BurndownChartProps {
  data: BurndownDataPoint[];
  sprintName: string;
}

export function BurndownChart({ data, sprintName }: BurndownChartProps) {
  // Calculate if on track (actual <= ideal for current day)
  // null means future day, so we filter for days with actual values
  const daysWithActual = data.filter((d) => d.actual !== null);
  const currentPoint = daysWithActual[daysWithActual.length - 1];
  const isOnTrack = currentPoint ? (currentPoint.actual ?? 0) <= currentPoint.ideal : true;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-lg',
              isOnTrack
                ? 'bg-[var(--color-success-muted)] text-[var(--color-success)]'
                : 'bg-[var(--color-warning-muted)] text-[var(--color-warning)]'
            )}
          >
            <Target className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-muted)]">
              Sprint Burndown
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">{sprintName}</p>
          </div>
        </div>

        <span
          className={cn(
            'text-xs px-2 py-1 rounded-full',
            isOnTrack
              ? 'bg-[var(--color-success-muted)] text-[var(--color-success)]'
              : 'bg-[var(--color-warning-muted)] text-[var(--color-warning)]'
          )}
        >
          {isOnTrack ? 'On Track' : 'Behind Schedule'}
        </span>
      </div>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <AreaChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="actualGradient" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-primary)"
                  stopOpacity={0.3}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-primary)"
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--color-border)"
              vertical={false}
            />
            <XAxis
              dataKey="day"
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
            <ReferenceLine y={0} stroke="var(--color-border)" />
            {/* Ideal line */}
            <Area
              type="linear"
              dataKey="ideal"
              stroke="var(--color-text-muted)"
              strokeDasharray="5 5"
              fill="none"
              strokeWidth={2}
              name="Ideal"
            />
            {/* Actual line */}
            <Area
              type="monotone"
              dataKey="actual"
              stroke="var(--color-primary)"
              fill="url(#actualGradient)"
              strokeWidth={2}
              name="Actual"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-4 pt-4 border-t border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <div className="h-0.5 w-4 bg-[var(--color-primary)]" />
          <span className="text-xs text-[var(--color-text-muted)]">Actual</span>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="h-0.5 w-4"
            style={{
              backgroundImage:
                'repeating-linear-gradient(90deg, var(--color-text-muted) 0 4px, transparent 4px 8px)',
            }}
          />
          <span className="text-xs text-[var(--color-text-muted)]">Ideal</span>
        </div>
      </div>
    </div>
  );
}
