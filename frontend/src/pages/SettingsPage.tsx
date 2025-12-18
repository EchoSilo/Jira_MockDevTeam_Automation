import { Moon, Sun, Monitor } from 'lucide-react';
import { Header } from '@/components/common';
import { useThemeStore } from '@/store';
import { cn } from '@/lib/utils';

export function SettingsPage() {
  const { theme, setTheme } = useThemeStore();

  return (
    <div className="min-h-screen">
      <Header title="Settings" subtitle="Customize your experience" />

      <div className="p-6 max-w-2xl">
        {/* Appearance Section */}
        <div className="card">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-4">
            Appearance
          </h2>

          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-[var(--color-text-secondary)] mb-3 block">
                Theme
              </label>
              <div className="grid grid-cols-3 gap-3">
                <button
                  onClick={() => setTheme('light')}
                  className={cn(
                    'flex flex-col items-center gap-2 p-4 rounded-lg border transition-all',
                    theme === 'light'
                      ? 'border-[var(--color-primary)] bg-[var(--color-primary-muted)]'
                      : 'border-[var(--color-border)] hover:border-[var(--color-border-hover)]'
                  )}
                >
                  <Sun
                    className={cn(
                      'h-6 w-6',
                      theme === 'light'
                        ? 'text-[var(--color-primary)]'
                        : 'text-[var(--color-text-muted)]'
                    )}
                  />
                  <span
                    className={cn(
                      'text-sm',
                      theme === 'light'
                        ? 'text-[var(--color-primary)]'
                        : 'text-[var(--color-text-secondary)]'
                    )}
                  >
                    Light
                  </span>
                </button>

                <button
                  onClick={() => setTheme('dark')}
                  className={cn(
                    'flex flex-col items-center gap-2 p-4 rounded-lg border transition-all',
                    theme === 'dark'
                      ? 'border-[var(--color-primary)] bg-[var(--color-primary-muted)]'
                      : 'border-[var(--color-border)] hover:border-[var(--color-border-hover)]'
                  )}
                >
                  <Moon
                    className={cn(
                      'h-6 w-6',
                      theme === 'dark'
                        ? 'text-[var(--color-primary)]'
                        : 'text-[var(--color-text-muted)]'
                    )}
                  />
                  <span
                    className={cn(
                      'text-sm',
                      theme === 'dark'
                        ? 'text-[var(--color-primary)]'
                        : 'text-[var(--color-text-secondary)]'
                    )}
                  >
                    Dark
                  </span>
                </button>

                <button
                  disabled
                  className={cn(
                    'flex flex-col items-center gap-2 p-4 rounded-lg border',
                    'border-[var(--color-border)] opacity-50 cursor-not-allowed'
                  )}
                >
                  <Monitor className="h-6 w-6 text-[var(--color-text-muted)]" />
                  <span className="text-sm text-[var(--color-text-muted)]">
                    System
                  </span>
                </button>
              </div>
              <p className="text-xs text-[var(--color-text-muted)] mt-2">
                System theme detection coming soon
              </p>
            </div>
          </div>
        </div>

        {/* About Section */}
        <div className="card mt-6">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-4">
            About
          </h2>
          <div className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <p>
              <span className="text-[var(--color-text-muted)]">Version:</span>{' '}
              1.0.0 (Prototype)
            </p>
            <p>
              <span className="text-[var(--color-text-muted)]">Stack:</span> React
              + TypeScript + Tailwind CSS
            </p>
            <p>
              <span className="text-[var(--color-text-muted)]">Backend:</span>{' '}
              FastAPI + CrewAI
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
