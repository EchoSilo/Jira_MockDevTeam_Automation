import { Activity as ActivityIcon, ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Activity } from '@/types';

interface ActivityFeedProps {
  activities: Activity[];
  jiraUrl?: string | null;
}

const ACTION_COLORS: Record<string, string> = {
  create_story: 'text-purple-400',
  pick_up_from_backlog: 'text-blue-400',
  progress_to_review: 'text-indigo-400',
  complete_code_review: 'text-cyan-400',
  qa_approve: 'text-green-400',
  qa_reject: 'text-red-400',
  inject_blocker: 'text-orange-400',
  resolve_blocker: 'text-emerald-400',
  default: 'text-[var(--color-text-secondary)]',
};

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString();
}

function formatActionType(actionType: string): string {
  if (!actionType) return 'Unknown';
  return actionType
    .split('_')
    .filter((word) => word)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export function ActivityFeed({ activities, jiraUrl }: ActivityFeedProps) {
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
            <ActivityIcon className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-muted)]">
              Recent Activity
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">
              Live updates from the team
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-3 max-h-80 overflow-y-auto">
        {activities.length === 0 ? (
          <div className="text-center py-8 text-[var(--color-text-muted)]">
            <ActivityIcon className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No recent activity</p>
          </div>
        ) : (
          activities.map((activity) => (
            <div
              key={activity.id}
              className={cn(
                'flex items-start gap-3 p-3 rounded-lg',
                'bg-[var(--color-surface-elevated)]',
                'border border-[var(--color-border)]',
                'transition-colors hover:border-[var(--color-border-hover)]'
              )}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-[var(--color-text-primary)]">
                    {activity.agentName}
                  </span>
                  <span
                    className={cn(
                      'text-xs',
                      ACTION_COLORS[activity.actionType] || ACTION_COLORS.default
                    )}
                  >
                    {formatActionType(activity.actionType)}
                  </span>
                </div>
                {activity.ticketKey && (
                  <a
                    href={jiraUrl ? `${jiraUrl.replace(/\/+$/, '')}/browse/${activity.ticketKey}` : '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(
                      "flex items-center gap-2 mt-1 group",
                      jiraUrl ? "cursor-pointer" : "cursor-default"
                    )}
                    onClick={(e) => !jiraUrl && e.preventDefault()}
                  >
                    <span className="text-xs text-[var(--color-primary)] font-mono group-hover:underline">
                      {activity.ticketKey}
                    </span>
                    <ExternalLink className="h-3 w-3 text-[var(--color-text-muted)] group-hover:text-[var(--color-primary)]" />
                  </a>
                )}
                {activity.details && (
                  <p className="text-xs text-[var(--color-text-muted)] mt-1 line-clamp-2">
                    {activity.details}
                  </p>
                )}
              </div>
              <span className="text-xs text-[var(--color-text-muted)] whitespace-nowrap">
                {formatTimestamp(activity.timestamp)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
