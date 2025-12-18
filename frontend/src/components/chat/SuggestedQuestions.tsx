import { cn } from '@/lib/utils';

interface SuggestedQuestionsProps {
  onSelect: (question: string) => void;
}

const SUGGESTIONS = [
  "What's the sprint status?",
  "Who's overloaded right now?",
  "Are there any blockers?",
  "What's in the backlog?",
  "Create a new story",
  "How are we tracking against the timeline?",
];

export function SuggestedQuestions({ onSelect }: SuggestedQuestionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {SUGGESTIONS.map((suggestion) => (
        <button
          key={suggestion}
          onClick={() => onSelect(suggestion)}
          className={cn(
            'px-3 py-1.5 text-xs rounded-full',
            'bg-[var(--color-surface)]',
            'border border-[var(--color-border)]',
            'text-[var(--color-text-secondary)]',
            'transition-colors duration-200',
            'hover:border-[var(--color-primary)]',
            'hover:text-[var(--color-primary)]'
          )}
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}
