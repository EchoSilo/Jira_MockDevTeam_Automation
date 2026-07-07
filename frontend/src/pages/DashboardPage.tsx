import { useEffect, useState } from 'react';
import { AlertTriangle, RefreshCw, WifiOff } from 'lucide-react';
import { Header, Tabs, TabsContent } from '@/components/common';
import {
  MetricCard,
  StatusBreakdownChart,
  ScenarioDistributionChart,
  ActiveScenariosCard,
  SprintOverviewCard,
  SprintHealthCard,
  FutureSprintsCard,
  WorkloadCard,
  VelocityChart,
  BurndownChart,
  ActivityFeed,
  ScenarioTimeline,
  VersionListCard,
  VersionProgressCard,
  ReleaseNotesCard,
  VersionIssuesCard,
  ReleaseNotesShelf,
  TagCloudCard,
  AssignmentTrendsCard,
} from '@/components/dashboard';
import { useDashboardStore, useReleaseNotesStore } from '@/store';
import {
  useDashboardData,
  useVersions,
  useVersionProgress,
  useVersionIssues,
  useGenerateReleaseNotes,
  useReleaseNotesHistory,
  useDownloadReleaseNotes,
  useFutureSprints,
  usePlanFutureSprintsMutation,
} from '@/hooks/useApi';
import type { OutputFormat } from '@/lib/api';
import {
  transformSprint,
  transformAgents,
  transformScenarioDistribution,
  transformRecentActions,
  countBlockers,
  countOverloadedAgents,
  getActivityContext,
  filterScenariosByTeam,
  getSprintScenarioFromResponse,
} from '@/lib/transformers';
import { cn } from '@/lib/utils';

export function DashboardPage() {
  const { selectedTeam } = useDashboardStore();

  // Release view state
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);

  // Auto-refresh is opt-in (off by default); preference persists across reloads.
  const [autoRefresh, setAutoRefresh] = useState(
    () => localStorage.getItem('dashboardAutoRefresh') === 'true'
  );
  useEffect(() => {
    localStorage.setItem('dashboardAutoRefresh', String(autoRefresh));
  }, [autoRefresh]);
  const AUTO_REFRESH_INTERVAL_MS = 15000;

  // Release notes store for shelf state
  const {
    isShelfOpen,
    closeShelf,
    activeNotes,
    setActiveNotes,
    openShelf,
  } = useReleaseNotesStore();

  // Fetch real data from backend. Polling only runs when auto-refresh is on
  // (0 disables the interval in useDashboardData/useApi).
  const { data, isLoading, error, refetch } = useDashboardData({
    refetchInterval: autoRefresh ? AUTO_REFRESH_INTERVAL_MS : 0,
  });

  const { health, state, agents, scenarios, sprintData } = data;

  // Release data hooks
  const { data: versionsData, isLoading: versionsLoading } = useVersions();
  const { data: progressData, isLoading: progressLoading } = useVersionProgress(selectedVersion);
  const { data: issuesData, isLoading: issuesLoading } = useVersionIssues(selectedVersion);
  const { generate: generateNotes, isLoading: notesLoading } = useGenerateReleaseNotes();
  const { data: historyData, refetch: refetchHistory } = useReleaseNotesHistory();
  const { download: downloadNotes, isDownloading } = useDownloadReleaseNotes();

  // Planning horizon (future sprints) data + on-demand planning
  const {
    data: futureSprintsData,
    isLoading: futureSprintsLoading,
    refetch: refetchFutureSprints,
  } = useFutureSprints({
    refetchInterval: autoRefresh ? AUTO_REFRESH_INTERVAL_MS : 0,
  });
  const { planFutureSprints, isLoading: isPlanningFuture } = usePlanFutureSprintsMutation();

  const handlePlanFutureSprints = async () => {
    try {
      await planFutureSprints();
      await refetchFutureSprints();
    } catch {
      // Error surfaced via the mutation hook; horizon refetch is best-effort.
    }
  };

  // Handle release notes generation
  const handleGenerateNotes = async (format: OutputFormat, regenerate?: boolean) => {
    if (!selectedVersion) return;

    try {
      const result = await generateNotes(selectedVersion, format, regenerate ?? false);
      if (result && (format === 'md' || format === 'txt')) {
        setActiveNotes(result);
        openShelf();
        refetchHistory(); // Refresh history list
      }
    } catch (err) {
      console.error('Failed to generate notes:', err);
    }
  };

  // Handle viewing existing notes
  const handleViewNotes = async (version: string) => {
    try {
      // Load notes from backend (will use cache)
      const result = await generateNotes(version, 'md', false);
      if (result) {
        setActiveNotes(result);
        openShelf();
      }
    } catch (err) {
      console.error('Failed to load notes:', err);
    }
  };

  // Handle download
  const handleDownload = async (version: string, format: OutputFormat) => {
    try {
      await downloadNotes(version, format);
    } catch (err) {
      console.error('Failed to download notes:', err);
    }
  };

  // Calculate unreleased versions count for badge
  const unreleasedCount = versionsData?.versions.filter(v => !v.released && !v.archived).length ?? 0;

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
              Make sure the backend server is running and reachable at this
              site's address.
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

  // Get sprint scenario if available (new sprint-level narrative)
  const sprintScenario = getSprintScenarioFromResponse(scenarios);

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
  const activityContext = agents
    ? getActivityContext(agents, selectedTeam)
    : { count: 0, subtitle: 'actions', isStaleData: false };

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

        {/* Refresh controls */}
        <div className="flex items-center justify-end gap-3 text-xs text-[var(--color-text-muted)]">
          {isLoading && (
            <span className="flex items-center gap-1">
              <RefreshCw className="h-3 w-3 animate-spin" />
              Refreshing...
            </span>
          )}
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-[var(--color-primary)] cursor-pointer"
            />
            <span>Auto-refresh (15s)</span>
          </label>
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[var(--color-surface-elevated)] text-[var(--color-text-primary)] hover:bg-[var(--color-primary)] hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={cn('h-3 w-3', isLoading && 'animate-spin')} />
            Refresh
          </button>
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
            value={activityContext.count}
            subtitle={activityContext.subtitle}
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

        {/* Tab-based view for Sprint, Release, and Simulation data */}
        <Tabs
          tabs={[
            { value: 'sprint', label: 'Sprint View' },
            { value: 'planning', label: 'Planning', badge: futureSprintsData?.planned_count || undefined },
            { value: 'release', label: 'Release View', badge: unreleasedCount || undefined },
            { value: 'simulation', label: 'Simulation', badge: activeScenarioCount }
          ]}
          defaultValue="sprint"
          className="space-y-6"
        >
          {/* Sprint View - Focus on real sprint data */}
          <TabsContent value="sprint" className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-6">
              <BurndownChart data={sprintData?.burndownData ?? []} sprintName={sprint.name} />
              <VelocityChart data={sprintData?.velocityData ?? []} />
              <WorkloadCard agents={filteredAgents} />
              <StatusBreakdownChart data={statusBreakdown} />
            </div>

            {/* Assignment Trends - full width chart */}
            <AssignmentTrendsCard selectedTeam={selectedTeam} />
          </TabsContent>

          {/* Planning View - Future sprints in the planning horizon */}
          <TabsContent value="planning" className="space-y-6">
            <FutureSprintsCard
              data={futureSprintsData ?? null}
              isLoading={futureSprintsLoading}
              onPlan={handlePlanFutureSprints}
              isPlanning={isPlanningFuture}
            />
          </TabsContent>

          {/* Release View - Fix versions and release notes */}
          <TabsContent value="release" className="space-y-6">
            {/* Grid layout: Version list | Progress + Issues | Release Notes */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
              {/* Column 1: Version list + Tag Cloud */}
              <div className="space-y-6">
                <VersionListCard
                  versions={versionsData?.versions ?? []}
                  selectedVersion={selectedVersion}
                  onSelectVersion={setSelectedVersion}
                  isLoading={versionsLoading}
                />
                <TagCloudCard history={historyData ?? []} />
              </div>

              {/* Column 2-3: Progress + Issues stacked */}
              <div className="lg:col-span-2 space-y-6">
                <VersionProgressCard
                  versionName={selectedVersion}
                  progress={progressData ?? null}
                  isLoading={progressLoading}
                />
                <VersionIssuesCard
                  versionName={selectedVersion}
                  issuesByType={issuesData?.issues_by_type ?? null}
                  issues={issuesData?.issues}
                  total={issuesData?.total ?? 0}
                  isLoading={issuesLoading}
                  jiraUrl={health?.jira_url}
                />
              </div>

              {/* Column 4: Release Notes */}
              <div>
                <ReleaseNotesCard
                  versionName={selectedVersion}
                  history={historyData ?? []}
                  isGenerating={notesLoading}
                  onGenerate={handleGenerateNotes}
                  onViewNotes={handleViewNotes}
                  onDownload={handleDownload}
                />
              </div>
            </div>

            {/* Release Notes Shelf (outside grid, full-page overlay) */}
            <ReleaseNotesShelf
              notes={activeNotes}
              isOpen={isShelfOpen}
              onClose={closeShelf}
              onDownload={(format) => {
                if (activeNotes?.version) {
                  handleDownload(activeNotes.version, format);
                }
              }}
              isDownloading={isDownloading}
            />
          </TabsContent>

          {/* Simulation View - Focus on simulation diagnostics */}
          <TabsContent value="simulation" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Column 1: Active Scenarios + Scenario Distribution */}
              <div className="space-y-6">
                <ActiveScenariosCard data={scenarioDistribution} sprintScenario={sprintScenario} />
                <ScenarioDistributionChart data={scenarioDistribution} />
              </div>

              {/* Column 2: Scenario Timeline */}
              <div>
                <ScenarioTimeline
                  scenarios={state ? Object.values(state.active_scenarios) : []}
                />
              </div>

              {/* Column 3: Recent Activity */}
              <div>
                <ActivityFeed activities={recentActivities} jiraUrl={health?.jira_url} />
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
