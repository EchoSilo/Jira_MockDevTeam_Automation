import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { FloatingChat } from '../chat/FloatingChat';
import { cn } from '@/lib/utils';

export function Layout() {
  return (
    <div className="min-h-screen bg-[var(--color-background)]">
      <Sidebar />

      <main
        className={cn(
          'ml-[var(--sidebar-width)]',
          'min-h-screen'
        )}
      >
        <Outlet />
      </main>

      <FloatingChat />
    </div>
  );
}
