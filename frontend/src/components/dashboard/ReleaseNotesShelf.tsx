import { useEffect, useCallback, useRef, useState } from 'react';
import { X, Download, GripVertical } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useReleaseNotesStore, MIN_SHELF_WIDTH, MAX_SHELF_WIDTH } from '@/store';
import { ReleaseTagBadge } from './ReleaseTagBadge';
import type { ReleaseNotesResponse, OutputFormat } from '@/lib/api';

interface ReleaseNotesShelfProps {
  notes: ReleaseNotesResponse | null;
  isOpen: boolean;
  onClose: () => void;
  onDownload: (format: OutputFormat) => void;
  isDownloading?: boolean;
}

const FORMAT_OPTIONS: { value: OutputFormat; label: string }[] = [
  { value: 'md', label: 'MD' },
  { value: 'txt', label: 'TXT' },
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'DOCX' },
  { value: 'pptx', label: 'PPTX' },
];

// Simple markdown to HTML converter
function markdownToHtml(md: string): string {
  return md
    .replace(/^### (.*$)/gim, '<h3 class="text-base font-semibold mt-4 mb-2">$1</h3>')
    .replace(/^## (.*$)/gim, '<h2 class="text-lg font-semibold mt-5 mb-3">$1</h2>')
    .replace(/^# (.*$)/gim, '<h1 class="text-xl font-bold mt-6 mb-3">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.*)$/gim, '<li class="ml-4 list-disc">$1</li>')
    .replace(/\n\n/g, '</p><p class="my-3">')
    .replace(/\n/g, '<br/>');
}

export function ReleaseNotesShelf({
  notes,
  isOpen,
  onClose,
  onDownload,
  isDownloading = false,
}: ReleaseNotesShelfProps) {
  const { activeTab, setActiveTab, shelfWidth, setShelfWidth } = useReleaseNotesStore();
  const [isResizing, setIsResizing] = useState(false);
  const shelfRef = useRef<HTMLDivElement>(null);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  // Handle escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Handle resize
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    startXRef.current = e.clientX;
    startWidthRef.current = shelfWidth;
  }, [shelfWidth]);

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const deltaX = startXRef.current - e.clientX;
      const newWidth = startWidthRef.current + deltaX;
      setShelfWidth(Math.max(MIN_SHELF_WIDTH, Math.min(MAX_SHELF_WIDTH, newWidth)));
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, setShelfWidth]);

  if (!isOpen || !notes) return null;

  return (
    <>
      {/* Backdrop overlay */}
      <div
        className="fixed inset-0 bg-black/30 z-30 transition-opacity"
        onClick={onClose}
      />

      {/* Shelf panel */}
      <div
        ref={shelfRef}
        className={cn(
          'fixed right-0 top-0 h-full z-40',
          'bg-[var(--color-background)] border-l border-[var(--color-border)]',
          'shadow-2xl flex flex-col',
          'animate-in slide-in-from-right duration-300'
        )}
        style={{ width: shelfWidth }}
      >
        {/* Resize handle */}
        <div
          className={cn(
            'absolute left-0 top-0 bottom-0 w-1 cursor-ew-resize',
            'hover:bg-[var(--color-primary)] transition-colors',
            'flex items-center justify-center group',
            isResizing && 'bg-[var(--color-primary)]'
          )}
          onMouseDown={handleMouseDown}
        >
          <div className="absolute -left-2 w-5 h-full flex items-center justify-center">
            <GripVertical className="h-4 w-4 text-[var(--color-text-muted)] opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)] truncate">
              {notes.version}
            </h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              {notes.issue_count} issues
              {notes.from_cache && ' (cached)'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-[var(--color-surface-elevated)] transition-colors"
          >
            <X className="h-5 w-5 text-[var(--color-text-muted)]" />
          </button>
        </div>

        {/* Tags */}
        {notes.tags && notes.tags.length > 0 && (
          <div className="px-6 py-3 border-b border-[var(--color-border)] flex flex-wrap gap-2">
            {notes.tags.map((tag, index) => (
              <ReleaseTagBadge key={index} tag={tag} size="md" />
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-[var(--color-border)]">
          <button
            onClick={() => setActiveTab('executive')}
            className={cn(
              'flex-1 px-4 py-3 text-sm font-medium transition-colors',
              activeTab === 'executive'
                ? 'text-[var(--color-primary)] border-b-2 border-[var(--color-primary)] bg-[var(--color-primary-muted)]'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
            )}
          >
            Executive Summary
          </button>
          <button
            onClick={() => setActiveTab('technical')}
            className={cn(
              'flex-1 px-4 py-3 text-sm font-medium transition-colors',
              activeTab === 'technical'
                ? 'text-[var(--color-primary)] border-b-2 border-[var(--color-primary)] bg-[var(--color-primary-muted)]'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
            )}
          >
            Technical Details
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div
            className="prose prose-sm dark:prose-invert max-w-none text-[var(--color-text-secondary)]"
            dangerouslySetInnerHTML={{
              __html: markdownToHtml(
                activeTab === 'executive' ? notes.executive_notes : notes.technical_notes
              ),
            }}
          />
        </div>

        {/* Download footer */}
        <div className="border-t border-[var(--color-border)] px-6 py-4">
          <div className="flex items-center gap-2">
            <Download className="h-4 w-4 text-[var(--color-text-muted)]" />
            <span className="text-sm text-[var(--color-text-muted)]">Download:</span>
            <div className="flex gap-1 flex-wrap">
              {FORMAT_OPTIONS.map((format) => (
                <button
                  key={format.value}
                  onClick={() => onDownload(format.value)}
                  disabled={isDownloading}
                  className={cn(
                    'px-3 py-1.5 text-xs font-medium rounded-md',
                    'bg-[var(--color-surface-elevated)] text-[var(--color-text-secondary)]',
                    'hover:bg-[var(--color-primary-muted)] hover:text-[var(--color-primary)]',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                    'transition-colors'
                  )}
                >
                  {format.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
