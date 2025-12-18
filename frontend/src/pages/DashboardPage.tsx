import { TicketCheck, AlertTriangle, Activity, RefreshCw, WifiOff } from 'lucide-react';
import { Header } from '@/components/common';
import {
  MetricCard,
  SprintStatusCard,
  StatusBreakdownChart,
  ScenarioDistributionChart,
  WorkloadCard,
  VelocityChart,
  BurndownChart,
  ActivityFeed,
} from '@/components/dashboard';
import { useDashboardStore } from '@/store';
import { useDashboardData } from '@/hooks/useApi';
import {
  transformSprint,
  transformAgents,
  calculateStatusBreakdown,
  transformScenarioDistribution,
  transformRecentActions,
  countBlockers,
  countOverloadedAgents,
  getSprintProgress,
  filterScenariosByTeam,
} from '@/lib/transformers';
import {
  mockVelocityData,
  mockBurndownData,
} from '@/lib/mockData';
import { cn } from '@/lib/utils';

export function DashboardPage() {
  const { selectedTeam } = useDashboardStore();

  // Fetch real data from backend with 15 second refresh
  const { data, isLoading, error, refetch } = useDashboardData({
    refetchInterval: 15000,
  });

  const { state, agents, scenarios } = data;

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

  const statusBreakdown = state
    ? calculateStatusBreakdown(state)
    : { backlog: 0, inProgress: 0, codeReview: 0, testing: 0, done: 0 };

  const scenarioDistribution = filteredScenarios
    ? transformScenarioDistribution(filteredScenarios)
    : { normalFlow: 0, blocker: 0, rework: 0, scopeCreep: 0, dependency: 0 };

  const filteredAgents = state && agents
    ? transformAgents(agents, state, selectedTeam)
    : [];

  const recentActivities = state ? transformRecentActions(state) : [];

  // Calculate metrics
  const totalItems = Object.values(statusBreakdown).reduce((a, b) => a + b, 0);
  const completedItems = statusBreakdown.done;
  const sprintProgress = state ? getSprintProgress(state) : 0;
  const activeScenarioCount = filteredScenarios?.active_count || 0;
  const blockedItems = filteredScenarios ? countBlockers(filteredScenarios) : 0;
  const overloadedCount = state ? countOverloadedAgents(state) : 0;

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

        {/* Top metric cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            title="Sprint Progress"
            value={`${sprintProgress}%`}
            subtitle={`${completedItems} of ${totalItems} items`}
            icon={<TicketCheck className="h-5 w-5" />}
            status={sprintProgress >= 80 ? 'success' : sprintProgress >= 50 ? 'default' : 'warning'}
          />
          <MetricCard
            title="Active Scenarios"
            value={activeScenarioCount}
            subtitle="Items in progress"
            icon={<Activity className="h-5 w-5" />}
          />
          <MetricCard
            title="Blockers"
            value={blockedItems}
            subtitle="Items blocked"
            icon={<AlertTriangle className="h-5 w-5" />}
            status={blockedItems > 0 ? 'warning' : 'success'}
          />
          <MetricCard
            title="Team Size"
            value={filteredAgents.length}
            subtitle={`${overloadedCount} overloaded`}
            status={overloadedCount > 0 ? 'warning' : 'default'}
          />
        </div>

        {/* Main dashboard grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column - Sprint and Status */}
          <div className="space-y-6">
            <SprintStatusCard sprint={sprint} />
            <ScenarioDistributionChart data={scenarioDistribution} />
          </div>

          {/* Middle column - Charts */}
          <div className="space-y-6">
            <StatusBreakdownChart data={statusBreakdown} />
            <VelocityChart data={mockVelocityData} />
          </div>

          {/* Right column - Workload */}
          <div className="space-y-6">
            <WorkloadCard agents={filteredAgents} />
          </div>
        </div>

        {/* Bottom row - Burndown and Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <BurndownChart data={mockBurndownData} sprintName={sprint.name} />
          <ActivityFeed activities={recentActivities} />
        </div>
      </div>
    </div>
  );
}
