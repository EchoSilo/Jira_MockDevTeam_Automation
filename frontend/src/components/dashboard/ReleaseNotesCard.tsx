import { useState } from 'react';
import { FileText, Download, RefreshCw, ChevronDown, Sparkles, Eye, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ReleaseTagBadge } from './ReleaseTagBadge';
import type { ReleaseNotesHistoryItem, OutputFormat } from '@/lib/api';

interface ReleaseNotesCardProps {
  versionName: string | null;
  history: ReleaseNotesHistoryItem[];
  isGenerating: boolean;
  onGenerate: (format: OutputFormat, regenerate?: boolean) => void;
  onViewNotes: (version: string) => void;
  onDownload: (version: string, format: OutputFormat) => void;
}

const FORMAT_OPTIONS: { value: OutputFormat; label: string; icon: string }[] = [
  { value: 'md', label: 'Markdown', icon: '#' },
  { value: 'txt', label: 'Plain Text', icon: 'T' },
  { value: 'pdf', label: 'PDF', icon: 'P' },
  { value: 'docx', label: 'Word Doc', icon: 'W' },
  { value: 'pptx', label: 'PowerPoint', icon: 'S' },
];

function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return 'Unknown date';
  }
}

export function ReleaseNotesCard({
  versionName,
  history,
  isGenerating,
  onGenerate,
  onViewNotes,
  onDownload,
}: ReleaseNotesCardProps) {
  const [showGenerateDropdown, setShowGenerateDropdown] = useState(false);
  const [showDownloadDropdown, setShowDownloadDropdown] = useState(false);

  // Find history item for selected version (if any)
  const selectedVersionHistory = versionName
    ? history.find((h) => h.version === versionName)
    : null;

  // Check if selected version has any generated notes
  const hasGeneratedNotes = selectedVersionHistory && selectedVersionHistory.file_formats.length > 0;

  if (!versionName) {
    return (
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              Release Notes
            </h3>
          </div>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">
          Select a version to generate or view release notes
        </p>
      </div>
    );
  }

  return (
    <div className="card h-full flex flex-col">
      {/* Header */}
      <div className="flex flex-col gap-3 mb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-info-muted)] text-[var(--color-info)]">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              Release Notes
            </h3>
            <p className="text-xs text-[var(--color-text-muted)]">
              {versionName}
            </p>
          </div>
        </div>

        {/* Action buttons - below header */}
        <div className="flex items-center gap-2">
          {/* Generate dropdown */}
          <div className="relative">
            <button
              onClick={() => {
                setShowGenerateDropdown(!showGenerateDropdown);
                setShowDownloadDropdown(false);
              }}
              disabled={isGenerating}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg text-sm',
                'bg-[var(--color-primary)] text-white',
                'hover:opacity-90',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {isGenerating ? (
                <RefreshCw className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              Generate
              <ChevronDown className="h-4 w-4" />
            </button>

            {showGenerateDropdown && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowGenerateDropdown(false)}
                />
                <div className="absolute right-0 mt-2 w-48 bg-[var(--color-surface-elevated)] rounded-lg shadow-lg border border-[var(--color-border)] z-20">
                  {FORMAT_OPTIONS.map((format) => (
                    <button
                      key={format.value}
                      onClick={() => {
                        onGenerate(format.value, false);
                        setShowGenerateDropdown(false);
                      }}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] first:rounded-t-lg"
                    >
                      <span className="w-5 h-5 rounded bg-[var(--color-surface)] flex items-center justify-center text-xs font-mono">
                        {format.icon}
                      </span>
                      {format.label}
                    </button>
                  ))}
                  {hasGeneratedNotes && (
                    <div className="border-t border-[var(--color-border)]">
                      <button
                        onClick={() => {
                          onGenerate('md', true);
                          setShowGenerateDropdown(false);
                        }}
                        className="w-full flex items-center gap-2 px-4 py-2 text-sm text-[var(--color-warning)] hover:bg-[var(--color-surface)] rounded-b-lg"
                      >
                        <RefreshCw className="h-4 w-4" />
                        Regenerate
                      </button>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Download dropdown */}
          <div className="relative">
            <button
              onClick={() => {
                setShowDownloadDropdown(!showDownloadDropdown);
                setShowGenerateDropdown(false);
              }}
              disabled={!hasGeneratedNotes || isGenerating}
              className={cn(
                'flex items-center gap-2 px-3 py-2 rounded-lg text-sm',
                'bg-[var(--color-surface-elevated)] text-[var(--color-text-secondary)]',
                'hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)]',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'border border-[var(--color-border)]'
              )}
            >
              <Download className="h-4 w-4" />
              Download
              <ChevronDown className="h-4 w-4" />
            </button>

            {showDownloadDropdown && hasGeneratedNotes && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowDownloadDropdown(false)}
                />
                <div className="absolute right-0 mt-2 w-48 bg-[var(--color-surface-elevated)] rounded-lg shadow-lg border border-[var(--color-border)] z-20">
                  {FORMAT_OPTIONS.filter((f) =>
                    selectedVersionHistory?.file_formats.includes(f.value)
                  ).map((format) => (
                    <button
                      key={format.value}
                      onClick={() => {
                        onDownload(versionName, format.value);
                        setShowDownloadDropdown(false);
                      }}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] first:rounded-t-lg last:rounded-b-lg"
                    >
                      <span className="w-5 h-5 rounded bg-[var(--color-surface)] flex items-center justify-center text-xs font-mono">
                        {format.icon}
                      </span>
                      {format.label}
                    </button>
                  ))}
                  {selectedVersionHistory?.file_formats.length === 0 && (
                    <div className="px-4 py-2 text-sm text-[var(--color-text-muted)]">
                      No formats available
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Previously generated notes for selected version */}
      {hasGeneratedNotes && (
        <div className="border-t border-[var(--color-border)] pt-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="h-4 w-4 text-[var(--color-text-muted)]" />
            <span className="text-xs font-medium text-[var(--color-text-muted)]">
              Generated Notes
            </span>
          </div>

          <div className="bg-[var(--color-surface)] rounded-lg p-3">
            <div className="flex items-start justify-between mb-2">
              <div>
                <p className="text-sm font-medium text-[var(--color-text-primary)]">
                  {selectedVersionHistory.version}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {formatDate(selectedVersionHistory.generated_at)} &bull;{' '}
                  {selectedVersionHistory.issue_count} issues
                </p>
              </div>
              <button
                onClick={() => onViewNotes(selectedVersionHistory.version)}
                className="flex items-center gap-1 px-2 py-1 text-xs rounded bg-[var(--color-primary-muted)] text-[var(--color-primary)] hover:opacity-80"
              >
                <Eye className="h-3 w-3" />
                View
              </button>
            </div>

            {/* Tags */}
            {selectedVersionHistory.tags && selectedVersionHistory.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {selectedVersionHistory.tags.map((tag, index) => (
                  <ReleaseTagBadge key={index} tag={tag} size="sm" />
                ))}
              </div>
            )}

            {/* Available formats */}
            <div className="flex items-center gap-1 mt-2 text-xs text-[var(--color-text-muted)]">
              <span>Formats:</span>
              {selectedVersionHistory.file_formats.map((format) => (
                <span
                  key={format}
                  className="px-1.5 py-0.5 rounded bg-[var(--color-surface-elevated)] uppercase"
                >
                  {format}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* History list (other versions) */}
      {history.length > 0 && (
        <div className="border-t border-[var(--color-border)] pt-4 mt-4">
          <div className="flex items-center gap-2 mb-3">
            <FileText className="h-4 w-4 text-[var(--color-text-muted)]" />
            <span className="text-xs font-medium text-[var(--color-text-muted)]">
              All Generated Releases ({history.length})
            </span>
          </div>

          <div className="max-h-48 overflow-y-auto space-y-2">
            {history.map((item) => (
              <div
                key={item.version}
                className={cn(
                  'rounded-lg p-2 cursor-pointer transition-colors',
                  item.version === versionName
                    ? 'bg-[var(--color-primary-muted)] border border-[var(--color-primary)]'
                    : 'bg-[var(--color-surface)] hover:bg-[var(--color-surface-elevated)]'
                )}
                onClick={() => onViewNotes(item.version)}
              >
                <div className="flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-[var(--color-text-primary)] truncate">
                      {item.version}
                    </p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {formatDate(item.generated_at)} &bull; {item.issue_count} issues
                    </p>
                  </div>
                  <Eye className="h-4 w-4 text-[var(--color-text-muted)] flex-shrink-0" />
                </div>

                {/* Mini tags */}
                {item.tags && item.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {item.tags.slice(0, 3).map((tag, index) => (
                      <span
                        key={index}
                        className="px-1.5 py-0.5 text-[10px] rounded-full bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]"
                      >
                        {tag}
                      </span>
                    ))}
                    {item.tags.length > 3 && (
                      <span className="text-[10px] text-[var(--color-text-muted)]">
                        +{item.tags.length - 3} more
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state when no history */}
      {!hasGeneratedNotes && history.length === 0 && (
        <div className="text-center py-4">
          <p className="text-sm text-[var(--color-text-muted)]">
            No release notes generated yet. Click "Generate" to create notes for this version.
          </p>
        </div>
      )}
    </div>
  );
}
