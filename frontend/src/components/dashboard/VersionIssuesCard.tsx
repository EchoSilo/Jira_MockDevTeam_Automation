import { Bug, BookOpen, CheckSquare, Layers, ListTodo } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { VersionIssue } from '@/lib/api';

interface VersionIssuesCardProps {
  versionName: string | null;
  issuesByType: Record<string, VersionIssue[]> | null;
  total: number;
  isLoading?: boolean;
  jiraUrl?: string | null;
}

// Issue type configuration
function getIssueTypeConfig(issueType: string): {
  color: string;
  label: string;
  icon: React.ReactNode;
} {
  const configs: Record<
    string,
    { color: string; label: string; icon: React.ReactNode }
  > = {
    Story: {
      color: '#10b981',
      label: 'Stories',
      icon: <BookOpen className="h-4 w-4" />,
    },
    Bug: {
      color: '#ef4444',
      label: 'Bugs',
      icon: <Bug className="h-4 w-4" />,
    },
    Task: {
      color: '#3b82f6',
      label: 'Tasks',
      icon: <CheckSquare className="h-4 w-4" />,
    },
    Epic: {
      color: '#8b5cf6',
      label: 'Epics',
      icon: <Layers className="h-4 w-4" />,
    },
    'Sub-task': {
      color: '#f59e0b',
      label: 'Sub-tasks',
      icon: <ListTodo className="h-4 w-4" />,
    },
    Subtask: {
      color: '#f59e0b',
      label: 'Sub-tasks',
      icon: <ListTodo className="h-4 w-4" />,
    },
  };
  return (
    configs[issueType] || {
      color: '#71717a',
      label: issueType,
      icon: <CheckSquare className="h-4 w-4" />,
    }
  );
}

export function VersionIssuesCard({
  versionName,
  issuesByType,
  total,
  isLoading,
  jiraUrl,
}: VersionIssuesCardProps) {
  if (!versionName) {
    return (
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]">
            <ListTodo className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              Issues
            </h3>
          </div>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">
          Select a version to view issues
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="card">
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div
              key={i}
              className="h-16 bg-[var(--color-surface-elevated)] rounded animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (!issuesByType || Object.keys(issuesByType).length === 0) {
    return (
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
            Issues in {versionName}
          </h3>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">
          No issues assigned to this version
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
          Issues in {versionName}
        </h3>
        <span className="text-xs text-[var(--color-text-muted)]">
          {total} total
        </span>
      </div>

      <div className="space-y-4 max-h-96 overflow-y-auto">
        {Object.entries(issuesByType).map(([type, issues]) => {
          const config = getIssueTypeConfig(type);
          return (
            <div key={type}>
              <div className="flex items-center gap-2 mb-2">
                <span style={{ color: config.color }}>{config.icon}</span>
                <h4
                  className="text-sm font-medium"
                  style={{ color: config.color }}
                >
                  {config.label} ({issues.length})
                </h4>
              </div>

              <div className="space-y-1 pl-6">
                {issues.map(issue => (
                  <div
                    key={issue.key}
                    className="flex items-center gap-2 py-1.5 text-sm"
                  >
                    {jiraUrl ? (
                      <a
                        href={`${jiraUrl}/browse/${issue.key}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[var(--color-primary)] hover:underline font-mono text-xs shrink-0"
                      >
                        {issue.key}
                      </a>
                    ) : (
                      <span className="font-mono text-xs text-[var(--color-primary)] shrink-0">
                        {issue.key}
                      </span>
                    )}
                    <span className="text-[var(--color-text-secondary)] truncate flex-1">
                      {issue.summary}
                    </span>
                    <span
                      className={cn(
                        'ml-auto text-xs px-2 py-0.5 rounded-full shrink-0',
                        issue.status.toLowerCase() === 'done'
                          ? 'bg-[var(--color-success-muted)] text-[var(--color-success)]'
                          : 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]'
                      )}
                    >
                      {issue.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
