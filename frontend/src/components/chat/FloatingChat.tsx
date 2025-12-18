import { MessageSquare, X, Minimize2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/store';
import { ChatContainer } from './ChatContainer';
import { PMSelector } from './PMSelector';

export function FloatingChat() {
  const { isFloatingChatOpen, setFloatingChatOpen } = useChatStore();

  if (!isFloatingChatOpen) {
    return (
      <button
        onClick={() => setFloatingChatOpen(true)}
        className={cn(
          'fixed bottom-6 right-6 z-50',
          'flex h-14 w-14 items-center justify-center',
          'rounded-full shadow-lg',
          'bg-[var(--color-primary)] text-white',
          'transition-transform duration-200',
          'hover:scale-110 hover:shadow-xl',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)] focus-visible:ring-offset-2'
        )}
        aria-label="Open chat"
      >
        <MessageSquare className="h-6 w-6" />
      </button>
    );
  }

  return (
    <div
      className={cn(
        'fixed bottom-6 right-6 z-50',
        'w-[400px] h-[600px]',
        'bg-[var(--color-background)]',
        'border border-[var(--color-border)]',
        'rounded-2xl shadow-2xl',
        'flex flex-col overflow-hidden',
        'animate-in slide-in-from-bottom-4 fade-in duration-300'
      )}
    >
      {/* Header */}
      <div
        className={cn(
          'flex items-center justify-between',
          'px-4 py-3',
          'border-b border-[var(--color-border)]',
          'bg-[var(--color-surface)]'
        )}
      >
        <PMSelector />
        <div className="flex items-center gap-1">
          <button
            onClick={() => setFloatingChatOpen(false)}
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-lg',
              'text-[var(--color-text-muted)]',
              'transition-colors hover:bg-[var(--color-surface-elevated)]',
              'hover:text-[var(--color-text-primary)]'
            )}
            aria-label="Minimize chat"
          >
            <Minimize2 className="h-4 w-4" />
          </button>
          <button
            onClick={() => setFloatingChatOpen(false)}
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-lg',
              'text-[var(--color-text-muted)]',
              'transition-colors hover:bg-[var(--color-error-muted)]',
              'hover:text-[var(--color-error)]'
            )}
            aria-label="Close chat"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Chat content */}
      <div className="flex-1 overflow-hidden">
        <ChatContainer />
      </div>
    </div>
  );
}
