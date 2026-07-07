import {
  CalendarClock,
  CalendarRange,
  CalendarX2,
  CircleUser,
  Gauge,
  Layers,
  RefreshCw,
  Target,
  Users,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type {
  FutureSprint,
  FutureSprintItem,
  FutureSprintsResponse,
  FutureSprintWorkload,
} from '@/lib/api';

interface FutureSprintsCardProps {
  data: FutureSprintsResponse | null;
  isLoading?: boolean;
  onPlan?: () => void;
  isPlanning?: boolean;
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return '—';
  }
}

function durationDays(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (Number.isNaN(s) || Number.isNaN(e)) return null;
  return Math.max(1, Math.round((e - s) / 86_400_000) + 1);
}

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  return Math.round((t - Date.now()) / 86_400_000);
}

function SprintPlanTile({ sprint, index }: { sprint: FutureSprint; index: number }) {
  const days = durationDays(sprint.start_date, sprint.end_date);
  const startsIn = daysUntil(sprint.start_date);
  const velocity = sprint.velocity_estimate;
  // Flag over-commitment vs the velocity estimate used when planning.
  const overCommitted =
    velocity != null && velocity > 0 && sprint.committed_points > velocity;

  return (
    <div className="card flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-primary-muted)] text-[var(--color-primary)]">
            <CalendarClock className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
              {sprint.name}
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">
              {index === 0 ? 'Next up' : `+${index} ahead`}
            </p>
          </div>
        </div>
        <span className="rounded-full bg-[var(--color-surface-elevated)] px-2 py-0.5 text-xs font-medium text-[var(--color-text-muted)]">
          Planned
        </span>
      </div>

      {/* Date range */}
      <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
        <CalendarRange className="h-4 w-4 shrink-0" />
        <span className="text-[var(--color-text-primary)]">
          {formatDate(sprint.start_date)} – {formatDate(sprint.end_date)}
        </span>
        {days != null && <span>· {days}d</span>}
        {startsIn != null && startsIn >= 0 && (
          <span>· starts in {startsIn}d</span>
        )}
      </div>

      {/* Commitment metrics */}
      <div className="grid grid-cols-3 gap-2">
        <div className="flex flex-col gap-0.5">
          <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
            <Target className="h-3.5 w-3.5" /> Points
          </span>
          <span
            className={cn(
              'text-lg font-semibold',
              overCommitted
                ? 'text-[var(--color-warning)]'
                : 'text-[var(--color-text-primary)]'
            )}
          >
            {sprint.committed_points}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
            <Layers className="h-3.5 w-3.5" /> Items
          </span>
          <span className="text-lg font-semibold text-[var(--color-text-primary)]">
            {sprint.committed_items.length}
          </span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
            <Gauge className="h-3.5 w-3.5" /> Velocity
          </span>
          <span className="text-lg font-semibold text-[var(--color-text-primary)]">
            {velocity != null ? velocity : '—'}
          </span>
        </div>
      </div>

      {overCommitted && (
        <p className="text-xs text-[var(--color-warning)]">
          Committed above the {velocity}-pt velocity estimate.
        </p>
      )}

      {/* Workload by assignee */}
      {sprint.workload.length > 0 && (
        <div className="flex flex-col gap-2">
          <span className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-muted)]">
            <Users className="h-3.5 w-3.5" /> Workload
          </span>
          <WorkloadBreakdown workload={sprint.workload} />
        </div>
      )}

      {/* Committed items — key + summary + assignee */}
      {sprint.items.length > 0 ? (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-muted)]">
            Committed items
          </span>
          <div className="flex max-h-52 flex-col divide-y divide-[var(--color-border)] overflow-y-auto">
            {sprint.items.map((item) => (
              <CommittedItemRow key={item.key} item={item} />
            ))}
          </div>
        </div>
      ) : sprint.committed_items.length > 0 ? (
        // Jira details unavailable — fall back to bare keys.
        <div className="flex flex-wrap gap-1">
          {sprint.committed_items.map((key) => (
            <span
              key={key}
              className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5 text-xs font-mono text-[var(--color-text-muted)]"
            >
              {key}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-xs italic text-[var(--color-text-muted)]">
          No backlog items committed yet.
        </p>
      )}
    </div>
  );
}

function WorkloadBreakdown({ workload }: { workload: FutureSprintWorkload[] }) {
  // Size bars by story points when the sprint has any estimated; otherwise fall
  // back to item count so the distribution is still visible for unpointed work.
  const totalPoints = workload.reduce((sum, w) => sum + w.points, 0);
  const usePoints = totalPoints > 0;
  const metric = (w: FutureSprintWorkload) => (usePoints ? w.points : w.item_count);
  const maxMetric = Math.max(1, ...workload.map(metric));
  return (
    <div className="flex flex-col gap-1.5">
      {workload.map((w) => (
        <div key={w.assignee} className="flex items-center gap-2">
          <span
            className="w-28 shrink-0 truncate text-xs text-[var(--color-text-primary)]"
            title={w.assignee}
          >
            {w.assignee}
          </span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-elevated)]">
            <div
              className={cn(
                'h-1.5 rounded-full',
                w.assignee === 'Unassigned'
                  ? 'bg-[var(--color-text-muted)]'
                  : 'bg-[var(--color-primary)]'
              )}
              style={{ width: `${(metric(w) / maxMetric) * 100}%` }}
            />
          </div>
          <span className="w-20 shrink-0 text-right text-xs text-[var(--color-text-muted)]">
            {w.item_count} item{w.item_count === 1 ? '' : 's'}
            {usePoints && ` · ${w.points}pt`}
          </span>
        </div>
      ))}
    </div>
  );
}

function CommittedItemRow({ item }: { item: FutureSprintItem }) {
  return (
    <div className="flex items-start gap-2 py-1.5">
      <span className="mt-0.5 shrink-0 font-mono text-xs text-[var(--color-primary)]">
        {item.key}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs text-[var(--color-text-primary)]" title={item.summary}>
          {item.summary || <span className="italic text-[var(--color-text-muted)]">No summary</span>}
        </p>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <span className="flex items-center gap-1">
            <CircleUser className="h-3 w-3" />
            {item.assignee ?? 'Unassigned'}
          </span>
          {item.status && (
            <span className="rounded bg-[var(--color-surface-elevated)] px-1.5 py-0.5">
              {item.status}
            </span>
          )}
          {item.points > 0 && <span>{item.points}pt</span>}
        </div>
      </div>
    </div>
  );
}

export function FutureSprintsCard({
  data,
  isLoading = false,
  onPlan,
  isPlanning = false,
}: FutureSprintsCardProps) {
  const sprints = data?.future_sprints ?? [];
  const target = data?.target ?? 3;
  const plannedCount = data?.planned_count ?? sprints.length;
  const needsPlanning = data?.needs_planning ?? false;

  const PlanButton = onPlan ? (
    <button
      type="button"
      onClick={onPlan}
      disabled={isPlanning}
      className={cn(
        'inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
        'bg-[var(--color-primary)] text-white hover:opacity-90',
        isPlanning && 'cursor-not-allowed opacity-60'
      )}
    >
      <RefreshCw className={cn('h-4 w-4', isPlanning && 'animate-spin')} />
      {isPlanning ? 'Planning…' : 'Plan future sprints'}
    </button>
  ) : null;

  return (
    <div className="space-y-6">
      {/* Summary header */}
      <div className="card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-primary-muted)] text-[var(--color-primary)]">
            <CalendarClock className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
              Planning Horizon
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">
              {plannedCount} of {target} future sprints planned
              {needsPlanning && plannedCount > 0 && (
                <span className="ml-2 rounded-full bg-[var(--color-warning-muted,var(--color-surface-elevated))] px-2 py-0.5 text-[var(--color-warning)]">
                  needs planning
                </span>
              )}
            </p>
          </div>
        </div>
        {PlanButton}
      </div>

      {/* Body */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-56 animate-pulse rounded-xl bg-[var(--color-surface-elevated)]"
            />
          ))}
        </div>
      ) : sprints.length === 0 ? (
        <div className="card flex flex-col items-center justify-center gap-4 py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]">
            <CalendarX2 className="h-7 w-7" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
              No future sprints planned
            </h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-[var(--color-text-muted)]">
              The planning horizon is empty — no upcoming sprints have been
              created or populated yet. PMs normally plan {target} sprints ahead
              on Wednesdays, or you can trigger it now.
            </p>
          </div>
          {PlanButton}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
          {sprints.map((sprint, i) => (
            <SprintPlanTile key={sprint.sprint_id} sprint={sprint} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
