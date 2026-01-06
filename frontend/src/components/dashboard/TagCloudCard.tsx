import { useMemo } from 'react';
import { Tags } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ReleaseTagBadge } from './ReleaseTagBadge';
import type { ReleaseNotesHistoryItem } from '@/lib/api';

interface TagCloudCardProps {
  history: ReleaseNotesHistoryItem[];
  onTagClick?: (tag: string) => void;
  className?: string;
}

interface TagCount {
  tag: string;
  count: number;
}

export function TagCloudCard({ history, onTagClick, className }: TagCloudCardProps) {
  // Aggregate tags across all releases
  const tagCounts = useMemo(() => {
    const counts: Record<string, number> = {};

    for (const release of history) {
      for (const tag of release.tags || []) {
        counts[tag] = (counts[tag] || 0) + 1;
      }
    }

    // Convert to sorted array (highest count first)
    const sorted: TagCount[] = Object.entries(counts)
      .map(([tag, count]) => ({ tag, count }))
      .sort((a, b) => b.count - a.count);

    return sorted;
  }, [history]);

  // Calculate min/max for sizing
  const maxCount = tagCounts.length > 0 ? Math.max(...tagCounts.map((t) => t.count)) : 1;
  const minCount = tagCounts.length > 0 ? Math.min(...tagCounts.map((t) => t.count)) : 1;

  // Get size class based on frequency
  const getSizeClass = (count: number): string => {
    if (maxCount === minCount) return 'text-sm';

    const ratio = (count - minCount) / (maxCount - minCount);

    if (ratio > 0.75) return 'text-lg font-semibold';
    if (ratio > 0.5) return 'text-base font-medium';
    if (ratio > 0.25) return 'text-sm';
    return 'text-xs';
  };

  if (tagCounts.length === 0) {
    return (
      <div className={cn('card', className)}>
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]">
            <Tags className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              Release Themes
            </h3>
          </div>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">
          No tags available. Generate release notes to see themes.
        </p>
      </div>
    );
  }

  return (
    <div className={cn('card', className)}>
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-primary-muted)] text-[var(--color-primary)]">
          <Tags className="h-5 w-5" />
        </div>
        <div>
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
            Release Themes
          </h3>
          <p className="text-xs text-[var(--color-text-muted)]">
            {tagCounts.length} unique tags across {history.length} releases
          </p>
        </div>
      </div>

      {/* Tag cloud */}
      <div className="flex flex-wrap gap-2 items-center justify-center py-2">
        {tagCounts.map(({ tag, count }) => (
          <button
            key={tag}
            onClick={() => onTagClick?.(tag)}
            className={cn(
              'inline-flex items-center gap-1 transition-transform hover:scale-105',
              getSizeClass(count)
            )}
          >
            <ReleaseTagBadge
              tag={tag}
              size={count === maxCount ? 'md' : 'sm'}
              onClick={() => onTagClick?.(tag)}
            />
            <span className="text-[var(--color-text-muted)] text-xs">
              ({count})
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
