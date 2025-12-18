import { useState, type KeyboardEvent } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  onSend: (message: string) => void;
  isSending?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  isSending = false,
  placeholder = 'Type a message...',
}: ChatInputProps) {
  const [value, setValue] = useState('');

  const handleSend = () => {
    if (value.trim() && !isSending) {
      onSend(value.trim());
      setValue('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className={cn(
        'flex items-end gap-2 p-3',
        'bg-[var(--color-surface)]',
        'border border-[var(--color-border)]',
        'rounded-xl'
      )}
    >
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={isSending}
        rows={1}
        className={cn(
          'flex-1 resize-none bg-transparent',
          'text-sm text-[var(--color-text-primary)]',
          'placeholder:text-[var(--color-text-muted)]',
          'focus:outline-none',
          'min-h-[24px] max-h-32'
        )}
        style={{
          height: 'auto',
          overflow: 'hidden',
        }}
        onInput={(e) => {
          const target = e.target as HTMLTextAreaElement;
          target.style.height = 'auto';
          target.style.height = `${Math.min(target.scrollHeight, 128)}px`;
        }}
      />

      <button
        onClick={handleSend}
        disabled={!value.trim() || isSending}
        className={cn(
          'flex h-8 w-8 items-center justify-center rounded-lg',
          'transition-colors duration-200',
          value.trim() && !isSending
            ? 'bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)]'
            : 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)]'
        )}
        aria-label="Send message"
      >
        {isSending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Send className="h-4 w-4" />
        )}
      </button>
    </div>
  );
}
