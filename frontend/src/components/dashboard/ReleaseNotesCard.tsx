import { useState } from 'react';
import { FileText, Download, RefreshCw, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ReleaseNotesResponse, OutputFormat } from '@/lib/api';

interface ReleaseNotesCardProps {
  versionName: string | null;
  notes: ReleaseNotesResponse | null;
  isGenerating: boolean;
  onGenerate: (format: OutputFormat, regenerate?: boolean) => void;
}

const FORMAT_OPTIONS: { value: OutputFormat; label: string; icon: string }[] = [
  { value: 'md', label: 'Markdown', icon: '#' },
  { value: 'txt', label: 'Plain Text', icon: 'T' },
  { value: 'pdf', label: 'PDF', icon: 'P' },
  { value: 'docx', label: 'Word Doc', icon: 'W' },
  { value: 'pptx', label: 'PowerPoint', icon: 'S' },
];

// Simple markdown to HTML converter
function markdownToHtml(md: string): string {
  return md
    .replace(/^### (.*$)/gim, '<h3 class="text-base font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 class="text-lg font-semibold mt-4 mb-2">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 class="text-xl font-bold mt-4 mb-2">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.*)$/gim, '<li class="ml-4">$1</li>')
    .replace(/\n\n/g, '</p><p class="my-2">')
    .replace(/\n/g, '<br/>');
}

export function ReleaseNotesCard({
  versionName,
  notes,
  isGenerating,
  onGenerate,
}: ReleaseNotesCardProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeTab, setActiveTab] = useState<'executive' | 'technical'>('executive');

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
          Select a version to generate release notes
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--color-info-muted)] text-[var(--color-info)]">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-medium text-[var(--color-text-primary)]">
              Release Notes
            </h3>
            {notes && (
              <p className="text-xs text-[var(--color-text-muted)]">
                {notes.issue_count} issues {notes.from_cache ? '(cached)' : ''}
              </p>
            )}
          </div>
        </div>

        {/* Export dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowDropdown(!showDropdown)}
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
              <Download className="h-4 w-4" />
            )}
            Export
            <ChevronDown className="h-4 w-4" />
          </button>

          {showDropdown && (
            <>
              {/* Backdrop to close dropdown */}
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowDropdown(false)}
              />
              <div className="absolute right-0 mt-2 w-48 bg-[var(--color-surface-elevated)] rounded-lg shadow-lg border border-[var(--color-border)] z-20">
                {FORMAT_OPTIONS.map(format => (
                  <button
                    key={format.value}
                    onClick={() => {
                      onGenerate(format.value, false);
                      setShowDropdown(false);
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)] first:rounded-t-lg"
                  >
                    <span className="w-5 h-5 rounded bg-[var(--color-surface)] flex items-center justify-center text-xs font-mono">
                      {format.icon}
                    </span>
                    {format.label}
                  </button>
                ))}
                <div className="border-t border-[var(--color-border)]">
                  <button
                    onClick={() => {
                      onGenerate('md', true);
                      setShowDropdown(false);
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-sm text-[var(--color-warning)] hover:bg-[var(--color-surface)] rounded-b-lg"
                  >
                    <RefreshCw className="h-4 w-4" />
                    Regenerate
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {notes ? (
        <div>
          {/* Tab buttons */}
          <div className="flex border-b border-[var(--color-border)] mb-4">
            <button
              onClick={() => setActiveTab('executive')}
              className={cn(
                'px-4 py-2 text-sm font-medium',
                activeTab === 'executive'
                  ? 'text-[var(--color-primary)] border-b-2 border-[var(--color-primary)]'
                  : 'text-[var(--color-text-muted)]'
              )}
            >
              Executive Summary
            </button>
            <button
              onClick={() => setActiveTab('technical')}
              className={cn(
                'px-4 py-2 text-sm font-medium',
                activeTab === 'technical'
                  ? 'text-[var(--color-primary)] border-b-2 border-[var(--color-primary)]'
                  : 'text-[var(--color-text-muted)]'
              )}
            >
              Technical Details
            </button>
          </div>

          {/* Content */}
          <div className="prose prose-sm dark:prose-invert max-h-64 overflow-y-auto text-[var(--color-text-secondary)]">
            <div
              dangerouslySetInnerHTML={{
                __html:
                  activeTab === 'executive'
                    ? markdownToHtml(notes.executive_notes)
                    : markdownToHtml(notes.technical_notes),
              }}
            />
          </div>
        </div>
      ) : (
        <div className="text-center py-8">
          <p className="text-sm text-[var(--color-text-muted)] mb-4">
            No release notes generated yet
          </p>
          <button
            onClick={() => onGenerate('md')}
            disabled={isGenerating}
            className="px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg hover:opacity-90 disabled:opacity-50"
          >
            {isGenerating ? 'Generating...' : 'Generate Notes'}
          </button>
        </div>
      )}
    </div>
  );
}
