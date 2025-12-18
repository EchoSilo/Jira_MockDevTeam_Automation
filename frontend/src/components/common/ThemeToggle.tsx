import { Moon, Sun } from 'lucide-react';
import { useThemeStore } from '@/store';
import { cn } from '@/lib/utils';

export function ThemeToggle() {
  const { theme, toggleTheme } = useThemeStore();

  return (
    <button
      onClick={toggleTheme}
      className={cn(
        'relative flex h-9 w-9 items-center justify-center rounded-lg',
        'transition-colors duration-200',
        'hover:bg-[var(--color-surface-elevated)]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]'
      )}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      <Sun
        className={cn(
          'h-5 w-5 transition-all duration-300',
          theme === 'dark'
            ? 'rotate-0 scale-100 text-[var(--color-text-secondary)]'
            : 'rotate-90 scale-0'
        )}
      />
      <Moon
        className={cn(
          'absolute h-5 w-5 transition-all duration-300',
          theme === 'light'
            ? 'rotate-0 scale-100 text-[var(--color-text-secondary)]'
            : '-rotate-90 scale-0'
        )}
      />
    </button>
  );
}
