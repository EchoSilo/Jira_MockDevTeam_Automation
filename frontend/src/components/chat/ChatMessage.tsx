import { User, Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
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

// Custom component to render ticket links within text
function TicketLink({ text }: { text: string }) {
  const ticketRegex = /([A-Z]+-\d+)/g;
  const parts = text.split(ticketRegex);

  return (
    <>
      {parts.map((part, index) => {
        if (ticketRegex.test(part)) {
          ticketRegex.lastIndex = 0;
          return (
            <span
              key={index}
              className="text-[var(--color-primary)] font-mono cursor-pointer hover:underline"
            >
              {part}
            </span>
          );
        }
        return part;
      })}
    </>
  );
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
          <div className="text-sm [&_p]:my-1 [&_ul]:my-2 [&_ul]:pl-4 [&_ul]:list-disc [&_li]:my-0.5 [&_strong]:font-semibold">
            <ReactMarkdown
              components={{
                p: ({ children }) => <p className="my-1"><TicketLink text={String(children)} /></p>,
                li: ({ children }) => <li><TicketLink text={String(children)} /></li>,
                strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        </div>
        <span className="text-xs text-[var(--color-text-muted)] mt-1">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
}
