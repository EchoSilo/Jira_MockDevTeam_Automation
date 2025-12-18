import { User, Bot } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatMessage as ChatMessageType } from '@/types';

interface ChatMessageProps {
  message: ChatMessageType;
}

function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Simple ticket link detection and rendering
function renderContent(content: string): React.ReactNode {
  // Match ticket keys like PROJ-123, ABC-456
  const ticketRegex = /([A-Z]+-\d+)/g;
  const parts = content.split(ticketRegex);

  return parts.map((part, index) => {
    if (ticketRegex.test(part)) {
      ticketRegex.lastIndex = 0; // Reset regex state
      return (
        <span
          key={index}
          className="text-[var(--color-primary)] font-mono text-sm cursor-pointer hover:underline"
        >
          {part}
        </span>
      );
    }
    return part;
  });
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex gap-3',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser
            ? 'bg-[var(--color-primary)]'
            : 'bg-[var(--color-surface-elevated)] border border-[var(--color-border)]'
        )}
      >
        {isUser ? (
          <User className="h-4 w-4 text-white" />
        ) : (
          <Bot className="h-4 w-4 text-[var(--color-primary)]" />
        )}
      </div>

      {/* Message bubble */}
      <div
        className={cn(
          'flex flex-col max-w-[70%]',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        {!isUser && message.pmName && (
          <span className="text-xs text-[var(--color-text-muted)] mb-1">
            {message.pmName}
          </span>
        )}
        <div
          className={cn(
            'rounded-2xl px-4 py-2.5',
            isUser
              ? 'bg-[var(--color-primary)] text-white rounded-br-sm'
              : 'bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text-primary)] rounded-bl-sm'
          )}
        >
          <p className="text-sm whitespace-pre-wrap">
            {renderContent(message.content)}
          </p>
        </div>
        <span className="text-xs text-[var(--color-text-muted)] mt-1">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
}
