import { AlertTriangle, RefreshCw, WifiOff } from 'lucide-react';
import Masonry from 'react-masonry-css';
import { Header, Tabs, TabsContent } from '@/components/common';
import {
  MetricCard,
  StatusBreakdownChart,
  ScenarioDistributionChart,
  ActiveScenariosCard,
  SprintOverviewCard,
  SprintHealthCard,
  WorkloadCard,
  VelocityChart,
  BurndownChart,
  ActivityFeed,
  ScenarioTimeline,
} from '@/components/dashboard';
import { useDashboardStore } from '@/store';
import { useDashboardData } from '@/hooks/useApi';
import {
  transformSprint,
  transformAgents,
  transformScenarioDistribution,
  transformRecentActions,
  countBlockers,
  countOverloadedAgents,
  getTodayActivityCount,
  filterScenariosByTeam,
} from '@/lib/transformers';
import { cn } from '@/lib/utils';

// Masonry breakpoint configuration for responsive layout
const breakpointColumns = {
  default: 3,  // Desktop: 3 columns
  1024: 2,     // Tablet: 2 columns
  640: 1,      // Mobile: 1 column
};

export function DashboardPage() {
  const { selectedTeam } = useDashboardStore();

  // Fetch real data from backend with 15 second refresh
  const { data, isLoading, error, refetch } = useDashboardData({
    refetchInterval: 15000,
  });

  const { state, agents, scenarios, sprintData } = data;

  // Show error state if backend is unavailable
  if (error && !state) {
    return (
      <div className="min-h-screen">
        <Header
          title="Dashboard"
          subtitle="Monitor sprint progress and team activity"
          showTeamFilter
        />
        <div className="p-6">
          <div className="card flex flex-col items-center justify-center py-16 text-center">
            <WifiOff className="h-12 w-12 text-[var(--color-text-muted)] mb-4" />
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2">
              Unable to Connect to Backend
            </h2>
            <p className="text-sm text-[var(--color-text-muted)] mb-4 max-w-md">
              Make sure the backend server is running at{' '}
              <code className="px-1 py-0.5 bg-[var(--color-surface-elevated)] rounded">
                http://localhost:8000
              </code>
            </p>
            <button
              onClick={() => refetch()}
              className="flex items-center gap-2 px-4 py-2 bg-[var(--color-primary)] text-white rounded-lg hover:bg-[var(--color-primary-hover)] transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Retry Connection
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Show loading skeleton on initial load
  if (isLoading && !state) {
    return (
      <div className="min-h-screen">
        <Header
          title="Dashboard"
          subtitle="Monitor sprint progress and team activity"
          showTeamFilter
        />
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="card animate-pulse">
                <div className="h-4 bg-[var(--color-surface-elevated)] rounded w-24 mb-2" />
                <div className="h-8 bg-[var(--color-surface-elevated)] rounded w-16 mb-2" />
                <div className="h-3 bg-[var(--color-surface-elevated)] rounded w-32" />
              </div>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="card h-64 animate-pulse">
                <div className="h-full bg-[var(--color-surface-elevated)] rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Calculate derived data from API response
  const sprint = state ? transformSprint(state) : { name: 'Sprint 1', number: 1, day: 1, totalDays: 7, startDate: new Date().toISOString() };

  const filteredScenarios = scenarios && agents
    ? filterScenariosByTeam(scenarios, agents, selectedTeam)
    : null;

  // Use real Jira status breakdown when available
  const statusBreakdown = sprintData?.statusBreakdown
    ?? { backlog: 0, inProgress: 0, codeReview: 0, testing: 0, done: 0 };

  const scenarioDistribution = filteredScenarios
    ? transformScenarioDistribution(filteredScenarios)
    : { normalFlow: 0, blocker: 0, rework: 0, scopeCreep: 0, dependency: 0 };

  const filteredAgents = state && agents
    ? transformAgents(agents, state, selectedTeam)
    : [];

  const recentActivities = state ? transformRecentActions(state) : [];

  // Calculate metrics - prefer real Jira sprint data when available
  const totalItems = sprint.totalItems ?? Object.values(statusBreakdown).reduce((a, b) => a + b, 0);
  const completedItems = sprint.doneItems ?? statusBreakdown.done;
  const sprintProgress = totalItems > 0 ? Math.round((completedItems / totalItems) * 100) : 0;
  const activeScenarioCount = filteredScenarios?.active_count || 0;
  const blockedItems = filteredScenarios ? countBlockers(filteredScenarios) : 0;
  const overloadedCount = state ? countOverloadedAgents(state) : 0;
  const todayActions = agents ? getTodayActivityCount(agents, selectedTeam) : 0;

  return (
    <div className="min-h-screen">
      <Header
        title="Dashboard"
        subtitle="Monitor sprint progress and team activity"
        showTeamFilter
      />

      <div className="p-6 space-y-6">
        {/* Connection status indicator */}
        {error && (
          <div className="flex items-center gap-2 px-3 py-2 bg-[var(--color-warning-muted)] text-[var(--color-warning)] rounded-lg text-sm">
            <AlertTriangle className="h-4 w-4" />
            <span>Connection issue - displaying cached data</span>
            <button
              onClick={() => refetch()}
              className="ml-auto underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        )}

        {/* Refresh indicator */}
        <div className="flex items-center justify-end text-xs text-[var(--color-text-muted)]">
          <RefreshCw
            className={cn('h-3 w-3 mr-1', isLoading && 'animate-spin')}
          />
          {isLoading ? 'Refreshing...' : 'Auto-refresh: 15s'}
        </div>

        {/* Top metric cards - 5 cards with Sprint Overview + Health */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <SprintOverviewCard
            sprint={sprint}
            completedItems={completedItems}
            totalItems={totalItems}
            progress={sprintProgress}
            compact
          />
          <MetricCard
            title="Today's Activity"
            value={todayActions}
            subtitle="actions"
            compact
          />
          <MetricCard
            title="Blockers"
            value={blockedItems}
            status={blockedItems > 0 ? 'warning' : 'success'}
            compact
          />
          <MetricCard
            title="Team Size"
            value={filteredAgents.length}
            subtitle={`${overloadedCount} overloaded`}
            status={overloadedCount > 0 ? 'warning' : 'default'}
            compact
          />
          <SprintHealthCard
            progress={sprintProgress}
            currentDay={sprint.day}
            totalDays={sprint.totalDays}
            compact
          />
        </div>

        {/* Tab-based view for Sprint and Simulation data */}
        <Tabs
          tabs={[
            { value: 'sprint', label: 'Sprint View' },
            { value: 'simulation', label: 'Simulation', badge: activeScenarioCount }
          ]}
          defaultValue="sprint"
          className="space-y-6"
        >
          {/* Sprint View - Focus on real sprint data */}
          <TabsContent value="sprint" className="space-y-6">
            <Masonry
              breakpointCols={breakpointColumns}
              className="masonry-grid"
              columnClassName="masonry-column"
            >
              <BurndownChart data={sprintData?.burndownData ?? []} sprintName={sprint.name} />
              <VelocityChart data={sprintData?.velocityData ?? []} />
              <WorkloadCard agents={filteredAgents} />
              <StatusBreakdownChart data={statusBreakdown} />
            </Masonry>
          </TabsContent>

          {/* Simulation View - Focus on simulation diagnostics */}
          <TabsContent value="simulation" className="space-y-6">
            <Masonry
              breakpointCols={breakpointColumns}
              className="masonry-grid"
              columnClassName="masonry-column"
            >
              <ScenarioTimeline
                scenarios={state ? Object.values(state.active_scenarios) : []}
              />
              <ActiveScenariosCard data={scenarioDistribution} />
              <ScenarioDistributionChart data={scenarioDistribution} />
              <ActivityFeed activities={recentActivities} />
            </Masonry>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
