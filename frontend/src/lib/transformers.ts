/**
 * Transform backend API data to frontend types
 */

import type {
  SimulationState,
  AgentsResponse,
  ScenariosResponse,
  AgentInfo,
  ScheduleInfo,
  SprintScenarioAPI,
} from './api';
import type {
  Sprint,
  Agent,
  StatusBreakdown,
  ScenarioDistribution,
  Activity,
  DashboardSnapshot,
  Team,
  SprintScenario,
} from '@/types';

// Map backend agent roles/names
const AGENT_NAMES: Record<string, string> = {
  alpha_pm: 'Sarah Chen',
  alpha_lead: 'Marcus Johnson',
  alpha_dev_senior: 'Elena Rodriguez',
  alpha_dev_mid: 'James Park',
  alpha_qa: 'Priya Sharma',
  beta_pm: 'David Kim',
  beta_dev_senior: 'Ana Costa',
  beta_dev_mid: 'Tyler Brooks',
  beta_qa: 'Rachel Green',
};

export function transformSprint(state: SimulationState): Sprint {
  // Prefer real Jira sprint data if available
  if (state.jira_sprint) {
    const jira = state.jira_sprint;
    // Calculate sprint day from dates
    const startDate = jira.start_date ? new Date(jira.start_date) : new Date();
    const endDate = jira.end_date ? new Date(jira.end_date) : new Date();
    const now = new Date();
    const totalDays = Math.ceil((endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24));
    const currentDay = Math.max(1, Math.ceil((now.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24)));

    return {
      name: jira.name,
      number: parseInt(jira.name.match(/\d+/)?.[0] || '1', 10),
      day: Math.min(currentDay, totalDays),
      totalDays: totalDays,
      startDate: jira.start_date || new Date().toISOString(),
      endDate: jira.end_date || undefined,
      totalItems: jira.total_issues,
      doneItems: jira.done_issues,
      isFromJira: true,
    };
  }

  // Fallback to local simulation sprint
  return {
    name: `Sprint ${state.sprint.sprint_number}`,
    number: state.sprint.sprint_number,
    day: state.sprint.sprint_day,
    totalDays: state.sprint.total_days,
    startDate: state.sprint.start_date || new Date().toISOString(),
    isFromJira: false,
  };
}

export function transformAgents(
  agentsResponse: AgentsResponse,
  state: SimulationState,
  filter: Team = 'all'
): Agent[] {
  return agentsResponse.agents
    .filter((agent) => filter === 'all' || agent.team === filter)
    .map((agent: AgentInfo) => ({
      id: agent.id,
      name: agent.name || AGENT_NAMES[agent.id] || agent.id,
      team: agent.team as Team,
      role: agent.role,
      assignedTickets: agent.current_workload,
      reviewTickets: agent.review_tickets?.length || 0,
      isOverloaded: state.agents[agent.id]?.is_overloaded || agent.current_workload >= 5,
      dailyActions: agent.daily_actions,
    }));
}

export function calculateStatusBreakdown(state: SimulationState): StatusBreakdown {
  const phases: Record<string, number> = {
    backlog: 0,
    inProgress: 0,
    codeReview: 0,
    testing: 0,
    done: 0,
  };

  Object.values(state.active_scenarios).forEach((scenario) => {
    const phase = scenario.current_phase.toLowerCase();

    if (phase.includes('backlog') || phase.includes('created')) {
      phases.backlog++;
    } else if (phase.includes('progress') || phase.includes('assigned') || phase.includes('fixing')) {
      phases.inProgress++;
    } else if (phase.includes('review') || phase.includes('re_review')) {
      phases.codeReview++;
    } else if (phase.includes('testing') || phase.includes('re_testing')) {
      phases.testing++;
    } else if (phase.includes('completed') || phase.includes('done')) {
      phases.done++;
    } else if (phase.includes('blocked') || phase.includes('waiting')) {
      // Count blocked items as in-progress for display
      phases.inProgress++;
    } else {
      // Default to backlog if unknown
      phases.backlog++;
    }
  });

  // Also count completed scenarios
  phases.done += state.completed_scenarios.length;

  return {
    backlog: phases.backlog,
    inProgress: phases.inProgress,
    codeReview: phases.codeReview,
    testing: phases.testing,
    done: phases.done,
  };
}

export function transformScenarioDistribution(
  scenarios: ScenariosResponse
): ScenarioDistribution {
  return {
    normalFlow: scenarios.distribution.normal_flow,
    blocker: scenarios.distribution.blocker,
    rework: scenarios.distribution.rework,
    scopeCreep: scenarios.distribution.scope_creep,
    dependency: scenarios.distribution.dependency,
  };
}

/**
 * Transform sprint scenario from API response to frontend type
 */
export function transformSprintScenario(
  apiScenario: SprintScenarioAPI | undefined
): SprintScenario | null {
  if (!apiScenario) return null;

  return {
    scenario_id: apiScenario.scenario_id,
    sprint_id: apiScenario.sprint_id,
    sprint_name: apiScenario.sprint_name,
    archetype: apiScenario.archetype as SprintScenario['archetype'],
    archetype_name: apiScenario.archetype_name,
    current_day: apiScenario.current_day,
    total_days: apiScenario.total_days,
    current_mood: apiScenario.current_mood,
    target_completion_rate: apiScenario.target_completion_rate,
    actual_completion_rate: apiScenario.actual_completion_rate,
    is_on_track: apiScenario.is_on_track,
    total_items: apiScenario.total_items,
    items_completed: apiScenario.items_completed,
    items_carried_over: apiScenario.items_carried_over,
    total_events: apiScenario.total_events,
    events_executed: apiScenario.events_executed,
    events_remaining: apiScenario.events_remaining,
    release_context: apiScenario.release_context,
    started_at: apiScenario.started_at,
    today_events: apiScenario.today_events.map((event) => ({
      event_id: event.event_id,
      event_type: event.event_type,
      ticket_key: event.ticket_key,
      executed: event.executed,
    })),
  };
}

/**
 * Extract sprint scenario from scenarios response if available
 */
export function getSprintScenarioFromResponse(
  scenarios: ScenariosResponse | null
): SprintScenario | null {
  if (!scenarios) return null;

  // Check if response contains a sprint scenario
  if (scenarios.type === 'sprint_scenario' && scenarios.sprint_scenario) {
    return transformSprintScenario(scenarios.sprint_scenario);
  }

  return null;
}

export function transformRecentActions(state: SimulationState): Activity[] {
  return state.recent_actions.slice(-20).reverse().map((action, idx) => ({
    id: `${action.timestamp}-${idx}`,
    timestamp: action.timestamp,
    agentId: action.agent_id,
    agentName: action.agent_name || AGENT_NAMES[action.agent_id] || action.agent_id,
    actionType: formatActionType(action.action_type),
    ticketKey: action.ticket_key || '',
    details: action.details || '',
  }));
}

function formatActionType(actionType: string): string {
  // Convert snake_case to human readable
  return actionType
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (l) => l.toUpperCase());
}

export function createDashboardSnapshot(
  state: SimulationState,
  agents: AgentsResponse,
  scenarios: ScenariosResponse,
  filter: Team = 'all'
): DashboardSnapshot {
  return {
    timestamp: new Date().toISOString(),
    sprint: transformSprint(state),
    statusBreakdown: calculateStatusBreakdown(state),
    workloadByAgent: transformAgents(agents, state, filter),
    activeScenarios: {
      total: scenarios.active_count,
      byType: transformScenarioDistribution(scenarios),
    },
    recentActions: transformRecentActions(state),
  };
}

// Calculate blockers count
export function countBlockers(scenarios: ScenariosResponse): number {
  // Handle sprint scenario format (no legacy scenarios array)
  if (!scenarios.scenarios) return 0;
  return scenarios.scenarios.filter((s) => s.is_blocked).length;
}

// Calculate overloaded agents
export function countOverloadedAgents(state: SimulationState): number {
  return Object.values(state.agents).filter((a) => a.is_overloaded).length;
}

// Get sprint progress percentage
export function getSprintProgress(state: SimulationState): number {
  const statusBreakdown = calculateStatusBreakdown(state);
  const total =
    statusBreakdown.backlog +
    statusBreakdown.inProgress +
    statusBreakdown.codeReview +
    statusBreakdown.testing +
    statusBreakdown.done;

  if (total === 0) return 0;
  return Math.round((statusBreakdown.done / total) * 100);
}

// Get total actions taken today across agents (optionally filtered by team)
export function getTodayActivityCount(
  agents: AgentsResponse,
  filter: Team = 'all'
): number {
  return agents.agents
    .filter((agent) => filter === 'all' || agent.team === filter)
    .reduce((sum, agent) => sum + agent.daily_actions, 0);
}

// Filter scenarios by team
export function filterScenariosByTeam(
  scenarios: ScenariosResponse,
  agents: AgentsResponse,
  team: Team
): ScenariosResponse {
  if (team === 'all') return scenarios;

  // Handle sprint scenario format (no legacy scenarios array)
  if (!scenarios.scenarios) {
    return scenarios;
  }

  const teamAgentIds = new Set(
    agents.agents.filter((a) => a.team === team).map((a) => a.id)
  );

  const filteredScenarios = scenarios.scenarios.filter(
    (s) => s.assigned_agent && teamAgentIds.has(s.assigned_agent)
  );

  // Recalculate distribution
  const distribution = {
    normal_flow: 0,
    blocker: 0,
    rework: 0,
    scope_creep: 0,
    dependency: 0,
  };

  filteredScenarios.forEach((s) => {
    const type = s.scenario_type as keyof typeof distribution;
    if (type in distribution) {
      distribution[type]++;
    }
  });

  return {
    active_count: filteredScenarios.length,
    scenarios: filteredScenarios,
    distribution,
  };
}

// ========== Schedule and Activity Context Helpers ==========

/**
 * Check if two dates are the same calendar day (in UTC)
 * Both dates are compared using UTC to avoid timezone mismatches
 */
function isSameDayUTC(date1: Date, date2: Date): boolean {
  return (
    date1.getUTCFullYear() === date2.getUTCFullYear() &&
    date1.getUTCMonth() === date2.getUTCMonth() &&
    date1.getUTCDate() === date2.getUTCDate()
  );
}

/**
 * Format a time for display (e.g., "2:30 PM")
 */
function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Format a date for display (e.g., "Dec 19")
 */
function formatShortDate(date: Date): string {
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Get day name (e.g., "Mon", "Tue")
 */
function getDayName(dayNumber: number): string {
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  // dayNumber is 1-7 (Mon-Sun), JavaScript getDay() is 0-6 (Sun-Sat)
  // Convert: 1->Mon(1), 7->Sun(0)
  const jsDay = dayNumber === 7 ? 0 : dayNumber;
  return days[jsDay];
}

/**
 * Convert JavaScript day (0=Sun) to our schedule day (1=Mon, 7=Sun)
 */
function jsToScheduleDay(jsDay: number): number {
  return jsDay === 0 ? 7 : jsDay;
}

/**
 * Get the next scheduled run time
 */
export function getNextScheduledRun(schedule: ScheduleInfo): string {
  const now = new Date();
  const currentHour = now.getHours();
  const currentScheduleDay = jsToScheduleDay(now.getDay());

  // Check if today is a scheduled day
  const isTodayScheduled = schedule.days.includes(currentScheduleDay);

  // If today is scheduled and we're before end hour, next run is today
  if (isTodayScheduled && currentHour < schedule.end_hour) {
    if (currentHour < schedule.start_hour) {
      return `Today ${schedule.start_hour > 12 ? schedule.start_hour - 12 : schedule.start_hour} ${schedule.start_hour >= 12 ? 'PM' : 'AM'}`;
    }
    // We're within schedule window - next run is soon
    return 'Within schedule';
  }

  // Find next scheduled day
  let daysAhead = 1;
  while (daysAhead <= 7) {
    const nextDate = new Date(now);
    nextDate.setDate(nextDate.getDate() + daysAhead);
    const nextScheduleDay = jsToScheduleDay(nextDate.getDay());

    if (schedule.days.includes(nextScheduleDay)) {
      const dayName = getDayName(nextScheduleDay);
      const hourStr = schedule.start_hour > 12
        ? `${schedule.start_hour - 12} PM`
        : schedule.start_hour === 12
          ? '12 PM'
          : `${schedule.start_hour} AM`;

      if (daysAhead === 1) {
        return `Tomorrow ${hourStr}`;
      }
      return `${dayName} ${hourStr}`;
    }
    daysAhead++;
  }

  return 'Unknown';
}

/**
 * Activity context for the dashboard, considering schedule
 */
export interface ActivityContext {
  count: number;
  subtitle: string;
  isStaleData: boolean;
}

/**
 * Get activity context based on last run and schedule
 */
export function getActivityContext(
  agents: AgentsResponse,
  filter: Team = 'all'
): ActivityContext {
  const lastRun = agents.last_run ? new Date(agents.last_run) : null;
  const now = new Date();
  const isToday = lastRun && isSameDayUTC(lastRun, now);

  // Calculate total actions from agents
  const totalActions = agents.agents
    .filter((agent) => filter === 'all' || agent.team === filter)
    .reduce((sum, agent) => sum + agent.daily_actions, 0);

  if (isToday) {
    // Data is from today - show actual count with last run time
    // Note: lastRun is in UTC, so we append UTC label for transparency
    return {
      count: totalActions,
      subtitle: `Last: ${formatTime(lastRun)} UTC`,
      isStaleData: false,
    };
  }

  // Data is stale (from a previous day)
  const schedule = agents.schedule;
  const nextRun = getNextScheduledRun(schedule);
  const lastRunStr = lastRun ? formatShortDate(lastRun) : 'Never';

  return {
    count: 0,
    subtitle: `Last: ${lastRunStr} · Next: ${nextRun}`,
    isStaleData: true,
  };
}
