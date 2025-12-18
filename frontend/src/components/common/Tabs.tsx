import * as TabsPrimitive from '@radix-ui/react-tabs';
import { cn } from '@/lib/utils';

interface Tab {
  value: string;
  label: string;
  badge?: number;
}

interface TabsProps {
  tabs: Tab[];
  defaultValue: string;
  children: React.ReactNode;
  className?: string;
}

export function Tabs({ tabs, defaultValue, children, className }: TabsProps) {
  return (
    <TabsPrimitive.Root defaultValue={defaultValue} className={className}>
      <TabsPrimitive.List className="flex border-b border-[var(--color-border)]">
        {tabs.map((tab) => (
          <TabsPrimitive.Trigger
            key={tab.value}
            value={tab.value}
            className={cn(
              'px-4 py-2 text-sm font-medium transition-colors',
              'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
              'data-[state=active]:text-[var(--color-primary)]',
              'data-[state=active]:border-b-2 data-[state=active]:border-[var(--color-primary)]'
            )}
          >
            <span className="flex items-center gap-2">
              {tab.label}
              {tab.badge !== undefined && (
                <span className="badge">{tab.badge}</span>
              )}
            </span>
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {children}
    </TabsPrimitive.Root>
  );
}

export const TabsContent = TabsPrimitive.Content;
