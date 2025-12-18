import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  Settings,
  Activity
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface NavItem {
  to: string;
  icon: React.ReactNode;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', icon: <LayoutDashboard className="h-5 w-5" />, label: 'Dashboard' },
  { to: '/chat', icon: <MessageSquare className="h-5 w-5" />, label: 'Chat with PM' },
];

const BOTTOM_ITEMS: NavItem[] = [
  { to: '/settings', icon: <Settings className="h-5 w-5" />, label: 'Settings' },
];

export function Sidebar() {
  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen',
        'w-[var(--sidebar-width)]',
        'bg-[var(--color-surface)]',
        'border-r border-[var(--color-border)]',
        'flex flex-col'
      )}
    >
      {/* Logo */}
      <div className="flex h-[var(--header-height)] items-center gap-3 px-6 border-b border-[var(--color-border)]">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-primary)]">
          <Activity className="h-5 w-5 text-white" />
        </div>
        <span className="text-lg font-semibold text-[var(--color-text-primary)]">
          Jira Sim
        </span>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg',
                    'text-sm font-medium transition-colors duration-200',
                    isActive
                      ? 'bg-[var(--color-primary-muted)] text-[var(--color-primary)]'
                      : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-elevated)]'
                  )
                }
              >
                {item.icon}
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* Bottom Navigation */}
      <div className="px-3 py-4 border-t border-[var(--color-border)]">
        <ul className="space-y-1">
          {BOTTOM_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-lg',
                    'text-sm font-medium transition-colors duration-200',
                    isActive
                      ? 'bg-[var(--color-primary-muted)] text-[var(--color-primary)]'
                      : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-elevated)]'
                  )
                }
              >
                {item.icon}
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
