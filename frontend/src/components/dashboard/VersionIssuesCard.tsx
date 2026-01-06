import { useState, useMemo } from 'react';
import { Bug, BookOpen, CheckSquare, Layers, ListTodo, ChevronRight, ChevronDown, FolderOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { VersionIssue } from '@/lib/api';

interface VersionIssuesCardProps {
  versionName: string | null;
  issuesByType: Record<string, VersionIssue[]> | null;
  issues?: VersionIssue[];
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
      label: 'Story',
      icon: <BookOpen className="h-4 w-4" />,
    },
    Bug: {
      color: '#ef4444',
      label: 'Bug',
      icon: <Bug className="h-4 w-4" />,
    },
    Task: {
      color: '#3b82f6',
      label: 'Task',
      icon: <CheckSquare className="h-4 w-4" />,
    },
    Epic: {
      color: '#8b5cf6',
      label: 'Epic',
      icon: <Layers className="h-4 w-4" />,
    },
    'Sub-task': {
      color: '#f59e0b',
      label: 'Sub-task',
      icon: <ListTodo className="h-4 w-4" />,
    },
    Subtask: {
      color: '#f59e0b',
      label: 'Sub-task',
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

interface HierarchyNode {
  issue: VersionIssue;
  children: VersionIssue[];
}

function buildHierarchy(issues: VersionIssue[]): { parents: HierarchyNode[]; noParent: VersionIssue[] } {
  // Create a map of all issues by key
  const issueMap = new Map<string, VersionIssue>();
  for (const issue of issues) {
    issueMap.set(issue.key, issue);
  }

  // Find parent issues (Epics or any issue that is a parent to others in this version)
  const parentKeys = new Set<string>();
  const childrenByParent = new Map<string, VersionIssue[]>();
  const orphans: VersionIssue[] = [];

  for (const issue of issues) {
    if (issue.parent_key) {
      parentKeys.add(issue.parent_key);
      const children = childrenByParent.get(issue.parent_key) || [];
      children.push(issue);
      childrenByParent.set(issue.parent_key, children);
    }
  }

  // Build parent nodes - include Epics and any parent that has children in this version
  const parents: HierarchyNode[] = [];
  const processedKeys = new Set<string>();

  // First, add all Epics that are in the version
  for (const issue of issues) {
    if (issue.issue_type === 'Epic') {
      parents.push({
        issue,
        children: childrenByParent.get(issue.key) || [],
      });
      processedKeys.add(issue.key);
    }
  }

  // Then, add "virtual" parent nodes for parents not in this version but have children here
  for (const parentKey of parentKeys) {
    if (!processedKeys.has(parentKey)) {
      const children = childrenByParent.get(parentKey) || [];
      if (children.length > 0) {
        // Check if the parent is in our issues list
        const parentIssue = issueMap.get(parentKey);
        if (parentIssue) {
          parents.push({
            issue: parentIssue,
            children,
          });
          processedKeys.add(parentKey);
        } else {
          // Parent not in version - create a placeholder
          const firstChild = children[0];
          parents.push({
            issue: {
              key: parentKey,
              summary: firstChild.parent_summary || `Parent: ${parentKey}`,
              issue_type: 'Epic', // Assume Epic for display purposes
              status: 'Unknown',
              assignee: null,
              priority: null,
              parent_key: null,
              parent_summary: null,
            },
            children,
          });
          processedKeys.add(parentKey);
        }
      }
    }
  }

  // Collect orphans - issues without parents that aren't already processed
  for (const issue of issues) {
    if (!issue.parent_key && !processedKeys.has(issue.key)) {
      orphans.push(issue);
    }
  }

  // Sort parents by key
  parents.sort((a, b) => a.issue.key.localeCompare(b.issue.key));

  return { parents, noParent: orphans };
}

function IssueRow({
  issue,
  jiraUrl,
  indented = false,
}: {
  issue: VersionIssue;
  jiraUrl?: string | null;
  indented?: boolean;
}) {
  const config = getIssueTypeConfig(issue.issue_type);

  return (
    <div
      className={cn(
        'flex items-center gap-2 py-2 text-sm hover:bg-[var(--color-surface-elevated)] rounded px-2 -mx-2',
        indented && 'ml-6'
      )}
    >
      <span style={{ color: config.color }} className="shrink-0">
        {config.icon}
      </span>
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
      <span className="text-[var(--color-text-secondary)] flex-1 min-w-0">
        {issue.summary}
      </span>
      <span
        className={cn(
          'text-xs px-2 py-0.5 rounded-full shrink-0',
          issue.status.toLowerCase() === 'done'
            ? 'bg-[var(--color-success-muted)] text-[var(--color-success)]'
            : 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]'
        )}
      >
        {issue.status}
      </span>
    </div>
  );
}

function ParentGroup({
  node,
  jiraUrl,
  defaultExpanded = false,
}: {
  node: HierarchyNode;
  jiraUrl?: string | null;
  defaultExpanded?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const config = getIssueTypeConfig(node.issue.issue_type);
  const childCount = node.children.length;

  return (
    <div className="border-b border-[var(--color-border)] last:border-b-0">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 py-2.5 px-2 -mx-2 hover:bg-[var(--color-surface-elevated)] rounded text-left"
      >
        <span className="text-[var(--color-text-muted)]">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </span>
        <span style={{ color: config.color }} className="shrink-0">
          {config.icon}
        </span>
        {jiraUrl ? (
          <a
            href={`${jiraUrl}/browse/${node.issue.key}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-[var(--color-primary)] hover:underline font-mono text-xs shrink-0"
          >
            {node.issue.key}
          </a>
        ) : (
          <span className="font-mono text-xs text-[var(--color-primary)] shrink-0">
            {node.issue.key}
          </span>
        )}
        <span className="text-[var(--color-text-primary)] font-medium flex-1 min-w-0 truncate">
          {node.issue.summary}
        </span>
        <span className="text-xs text-[var(--color-text-muted)] shrink-0">
          {childCount} {childCount === 1 ? 'child' : 'children'}
        </span>
        <span
          className={cn(
            'text-xs px-2 py-0.5 rounded-full shrink-0',
            node.issue.status.toLowerCase() === 'done'
              ? 'bg-[var(--color-success-muted)] text-[var(--color-success)]'
              : 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]'
          )}
        >
          {node.issue.status}
        </span>
      </button>

      {isExpanded && node.children.length > 0 && (
        <div className="pb-2">
          {node.children.map((child) => (
            <IssueRow key={child.key} issue={child} jiraUrl={jiraUrl} indented />
          ))}
        </div>
      )}
    </div>
  );
}

export function VersionIssuesCard({
  versionName,
  issuesByType,
  issues,
  total,
  isLoading,
  jiraUrl,
}: VersionIssuesCardProps) {
  // Build flat issues list from issuesByType if issues not provided
  const allIssues = useMemo(() => {
    if (issues) return issues;
    if (!issuesByType) return [];
    return Object.values(issuesByType).flat();
  }, [issues, issuesByType]);

  // Build hierarchy
  const hierarchy = useMemo(() => buildHierarchy(allIssues), [allIssues]);

  if (!versionName) {
    return (
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]">
            <ListTodo className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              Issues in Release
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
          {[1, 2, 3, 4, 5].map(i => (
            <div
              key={i}
              className="h-12 bg-[var(--color-surface-elevated)] rounded animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (allIssues.length === 0) {
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

      <div className="space-y-1">
        {/* Parent groups (Epics and other parents) */}
        {hierarchy.parents.map((node) => (
          <ParentGroup
            key={node.issue.key}
            node={node}
            jiraUrl={jiraUrl}
            defaultExpanded={hierarchy.parents.length <= 3}
          />
        ))}

        {/* No Parent group */}
        {hierarchy.noParent.length > 0 && (
          <NoParentGroup
            issues={hierarchy.noParent}
            jiraUrl={jiraUrl}
            defaultExpanded={hierarchy.parents.length === 0}
          />
        )}
      </div>
    </div>
  );
}

function NoParentGroup({
  issues,
  jiraUrl,
  defaultExpanded = false,
}: {
  issues: VersionIssue[];
  jiraUrl?: string | null;
  defaultExpanded?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className="border-b border-[var(--color-border)] last:border-b-0">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 py-2.5 px-2 -mx-2 hover:bg-[var(--color-surface-elevated)] rounded text-left"
      >
        <span className="text-[var(--color-text-muted)]">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </span>
        <span className="text-[var(--color-text-muted)] shrink-0">
          <FolderOpen className="h-4 w-4" />
        </span>
        <span className="text-[var(--color-text-secondary)] font-medium flex-1 min-w-0">
          No Epic
        </span>
        <span className="text-xs text-[var(--color-text-muted)] shrink-0">
          {issues.length} {issues.length === 1 ? 'issue' : 'issues'}
        </span>
      </button>

      {isExpanded && (
        <div className="pb-2">
          {issues.map((issue) => (
            <IssueRow key={issue.key} issue={issue} jiraUrl={jiraUrl} indented />
          ))}
        </div>
      )}
    </div>
  );
}
