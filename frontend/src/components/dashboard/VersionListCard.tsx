import { Package, CheckCircle, Clock, Archive } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { VersionInfo } from '@/lib/api';

interface VersionListCardProps {
  versions: VersionInfo[];
  selectedVersion: string | null;
  onSelectVersion: (name: string) => void;
  isLoading?: boolean;
}

type VersionStatus = 'released' | 'unreleased' | 'archived';

function getVersionStatus(v: VersionInfo): VersionStatus {
  if (v.archived) return 'archived';
  if (v.released) return 'released';
  return 'unreleased';
}

function getStatusIcon(status: VersionStatus) {
  switch (status) {
    case 'released':
      return <CheckCircle className="h-4 w-4 text-[var(--color-success)]" />;
    case 'unreleased':
      return <Clock className="h-4 w-4 text-[var(--color-info)]" />;
    case 'archived':
      return <Archive className="h-4 w-4 text-[var(--color-text-muted)]" />;
  }
}

function VersionItem({
  version,
  isSelected,
  onClick,
}: {
  version: VersionInfo;
  isSelected: boolean;
  onClick: () => void;
}) {
  const status = getVersionStatus(version);
  const icon = getStatusIcon(status);

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors text-left',
        isSelected
          ? 'bg-[var(--color-primary-muted)] text-[var(--color-primary)]'
          : 'hover:bg-[var(--color-surface-elevated)] text-[var(--color-text-secondary)]'
      )}
    >
      {icon}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{version.name}</p>
        {version.release_date && (
          <p className="text-xs text-[var(--color-text-muted)]">
            {new Date(version.release_date).toLocaleDateString()}
          </p>
        )}
      </div>
    </button>
  );
}

export function VersionListCard({
  versions,
  selectedVersion,
  onSelectVersion,
  isLoading,
}: VersionListCardProps) {
  const groupedVersions = {
    unreleased: versions.filter(v => getVersionStatus(v) === 'unreleased'),
    released: versions.filter(v => getVersionStatus(v) === 'released'),
    archived: versions.filter(v => getVersionStatus(v) === 'archived'),
  };

  return (
    <div className="card">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-primary-muted)] text-[var(--color-primary)]">
          <Package className="h-5 w-5" />
        </div>
        <div>
          <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
            Versions
          </h3>
          <p className="text-xs text-[var(--color-text-muted)]">
            {versions.length} total
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => (
            <div
              key={i}
              className="h-12 bg-[var(--color-surface-elevated)] rounded animate-pulse"
            />
          ))}
        </div>
      ) : (
        <div className="space-y-4 max-h-80 overflow-y-auto">
          {/* Unreleased versions first */}
          {groupedVersions.unreleased.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-2">
                Unreleased
              </h4>
              <div className="space-y-1">
                {groupedVersions.unreleased.map(version => (
                  <VersionItem
                    key={version.id}
                    version={version}
                    isSelected={selectedVersion === version.name}
                    onClick={() => onSelectVersion(version.name)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Released versions */}
          {groupedVersions.released.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-2">
                Released
              </h4>
              <div className="space-y-1">
                {groupedVersions.released.map(version => (
                  <VersionItem
                    key={version.id}
                    version={version}
                    isSelected={selectedVersion === version.name}
                    onClick={() => onSelectVersion(version.name)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Archived versions (if any) */}
          {groupedVersions.archived.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-2">
                Archived
              </h4>
              <div className="space-y-1">
                {groupedVersions.archived.map(version => (
                  <VersionItem
                    key={version.id}
                    version={version}
                    isSelected={selectedVersion === version.name}
                    onClick={() => onSelectVersion(version.name)}
                  />
                ))}
              </div>
            </div>
          )}

          {versions.length === 0 && (
            <p className="text-sm text-[var(--color-text-muted)] text-center py-4">
              No versions found
            </p>
          )}
        </div>
      )}
    </div>
  );
}
