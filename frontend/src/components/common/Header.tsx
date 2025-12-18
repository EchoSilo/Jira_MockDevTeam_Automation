import { ThemeToggle } from './ThemeToggle';
import { TeamFilter } from './TeamFilter';
import { cn } from '@/lib/utils';

interface HeaderProps {
  title: string;
  subtitle?: string;
  showTeamFilter?: boolean;
}

export function Header({ title, subtitle, showTeamFilter = false }: HeaderProps) {
  return (
    <header
      className={cn(
        'sticky top-0 z-30',
        'h-[var(--header-height)]',
        'bg-[var(--color-background)]/80 backdrop-blur-sm',
        'border-b border-[var(--color-border)]',
        'flex items-center justify-between',
        'px-6'
      )}
    >
      <div className="flex flex-col">
        <h1 className="text-xl font-semibold text-[var(--color-text-primary)]">
          {title}
        </h1>
        {subtitle && (
          <p className="text-sm text-[var(--color-text-muted)]">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-4">
        {showTeamFilter && <TeamFilter />}
        <ThemeToggle />
      </div>
    </header>
  );
}
