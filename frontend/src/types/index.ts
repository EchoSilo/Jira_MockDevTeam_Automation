// Theme types
export type Theme = 'dark' | 'light';

// Team types
export type Team = 'all' | 'alpha' | 'beta';

// Agent types
export interface Agent {
  id: string;
  name: string;
  team: Team;
  role: 'pm' | 'developer' | 'qa' | 'tech_lead';
  avatar?: string;
  assignedTickets: number;
  reviewTickets: number;  // Tickets being reviewed (for Tech Lead)
  isOverloaded: boolean;
  dailyActions: number;
}

// Sprint types
export interface Sprint {
  name: string;
  number: number;
  day: number;
  totalDays: number;
  startDate: string;
  endDate?: string;
  totalItems?: number;
  doneItems?: number;
  isFromJira?: boolean;  // Indicates if this is real Jira data
}

// Status breakdown
export interface StatusBreakdown {
  backlog: number;
  inProgress: number;
  codeReview: number;
  testing: number;
  done: number;
}

// Legacy scenario types (deprecated)
export type ScenarioType = 'normal_flow' | 'blocker' | 'rework' | 'scope_creep' | 'dependency';

export interface ScenarioDistribution {
  normalFlow: number;
  blocker: number;
  rework: number;
  scopeCreep: number;
  dependency: number;
}

// Sprint Scenario types (NEW)
export type ScenarioArchetype =
  | 'smooth_sprint'
  | 'overloaded_sprint'
  | 'blocker_heavy'
  | 'rework_sprint'
  | 'crunch_sprint'
  | 'recovery_sprint';

export interface SprintScenarioEvent {
  event_id: string;
  event_type: string;
  ticket_key: string | null;
  executed: boolean;
}

export interface SprintScenario {
  scenario_id: string;
  sprint_id: number;
  sprint_name: string;
  archetype: ScenarioArchetype;
  archetype_name: string;
  current_day: number;
  total_days: number;
  current_mood: string | null;
  target_completion_rate: number;
  actual_completion_rate: number;
  is_on_track: boolean;
  total_items: number;
  items_completed: number;
  items_carried_over: number;
  total_events: number;
  events_executed: number;
  events_remaining: number;
  release_context: string | null;
  started_at: string | null;
  today_events: SprintScenarioEvent[];
}

// Activity types
export interface Activity {
  id: string;
  timestamp: string;
  agentId: string;
  agentName: string;
  actionType: string;
  ticketKey: string;
  details: string;
}

// Dashboard snapshot
export interface DashboardSnapshot {
  timestamp: string;
  sprint: Sprint;
  statusBreakdown: StatusBreakdown;
  workloadByAgent: Agent[];
  activeScenarios: {
    total: number;
    byType: ScenarioDistribution;
  };
  recentActions: Activity[];
}

// Chat types
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  pmName?: string;
  ticketsMentioned?: string[];
}

export interface Conversation {
  id: string;
  pmId: string;
  pmName: string;
  messages: ChatMessage[];
  startedAt: string;
}

// Velocity data for charts
export interface VelocityDataPoint {
  sprintNumber: number;
  sprintName: string;
  completedItems: number;
}

// Burndown data for charts
export interface BurndownDataPoint {
  day: string;
  ideal: number;
  actual: number | null;  // null for future days
}
