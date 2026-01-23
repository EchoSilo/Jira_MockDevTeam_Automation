import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from 'recharts';
import { Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AssignmentTrendsResponse } from '@/lib/api';

interface AssignmentTrendsChartProps {
  data: AssignmentTrendsResponse | null;
  isLoading: boolean;
}

// Color palette for agents - consistent, distinguishable colors
const AGENT_COLORS = [
  '#3b82f6', // blue
  '#10b981', // emerald
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#ec4899', // pink
  '#06b6d4', // cyan
  '#84cc16', // lime
  '#f97316', // orange
  '#6366f1', // indigo
];

export function AssignmentTrendsChart({ data, isLoading }: AssignmentTrendsChartProps) {
  // Transform data for Recharts
  const chartData = data?.data_points.map((point) => ({
    date: point.date,
    ...point.assignments_by_agent,
  })) ?? [];

  // Get agent colors
  const agents = data?.agents ?? [];
  const getAgentColor = (index: number) => AGENT_COLORS[index % AGENT_COLORS.length];

  // Calculate total assignments for badge
  const totalAssignments = chartData.reduce((sum, point) => {
    return sum + Object.values(point).reduce((s, v) => {
      if (typeof v === 'number') return s + v;
      return s;
    }, 0);
  }, 0);

  const avgPerPeriod = chartData.length > 0
    ? Math.round(totalAssignments / chartData.length)
    : 0;

  if (isLoading) {
    return (
      <div className="animate-pulse">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-10 w-10 rounded-lg bg-[var(--color-surface-elevated)]" />
          <div className="space-y-2">
            <div className="h-4 w-32 rounded bg-[var(--color-surface-elevated)]" />
            <div className="h-3 w-24 rounded bg-[var(--color-surface-elevated)]" />
          </div>
        </div>
        <div className="h-64 rounded bg-[var(--color-surface-elevated)]" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex h-10 w-10 items-center justify-center rounded-lg',
              'bg-[var(--color-primary-muted)]',
              'text-[var(--color-primary)]'
            )}
          >
            <Users className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-muted)]">
              Assignment Trends
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">
              Tickets assigned per person over time
            </p>
          </div>
        </div>

        {avgPerPeriod > 0 && (
          <span
            className={cn(
              'text-xs px-2 py-1 rounded-full',
              'bg-[var(--color-primary-muted)] text-[var(--color-primary)]'
            )}
          >
            ~{avgPerPeriod} avg/period
          </span>
        )}
      </div>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1} debounce={50}>
          <AreaChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--color-border)"
              vertical={false}
            />
            <XAxis
              dataKey="date"
              axisLine={false}
              tickLine={false}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
              interval="preserveStartEnd"
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
              formatter={(value, name) => [value ?? 0, name]}
              labelFormatter={(label) => `Period: ${label}`}
            />
            <Legend
              wrapperStyle={{ fontSize: '11px' }}
              iconType="circle"
              iconSize={8}
            />
            {agents.map((agent, idx) => (
              <Area
                key={agent}
                type="monotone"
                dataKey={agent}
                stackId="1"
                stroke={getAgentColor(idx)}
                fill={getAgentColor(idx)}
                fillOpacity={0.6}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Insights section */}
      {data?.insights && (
        <div className="mt-4 space-y-2">
          {data.insights.unassigned_agents.length > 0 && (
            <div className="text-xs text-[var(--color-text-muted)] bg-[var(--color-warning-muted)] px-3 py-2 rounded-lg">
              <span className="font-medium">No assignments:</span>{' '}
              {data.insights.unassigned_agents.join(', ')}
            </div>
          )}
          {data.insights.consistently_overloaded.length > 0 && (
            <div className="text-xs text-[var(--color-text-muted)] bg-[var(--color-error-muted)] px-3 py-2 rounded-lg">
              <span className="font-medium">Consistently overloaded (5+ avg):</span>{' '}
              {data.insights.consistently_overloaded.join(', ')}
            </div>
          )}
          {data.insights.error && (
            <div className="text-xs text-[var(--color-error)] bg-[var(--color-error-muted)] px-3 py-2 rounded-lg">
              Error: {data.insights.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
