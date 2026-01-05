/**
 * API Service Layer for Jira Team Simulator Backend
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Types matching backend models
export interface HealthResponse {
  status: 'healthy' | 'degraded';
  jira_connected: boolean;
  last_run: string | null;
  simulation_day: number;
  jira_url: string | null;
}

export interface SprintState {
  sprint_number: number;
  sprint_day: number;
  total_days: number;
  start_date: string | null;
}

export interface JiraSprint {
  id: number;
  name: string;
  state: string;
  start_date: string | null;
  end_date: string | null;
  total_issues: number;
  done_issues: number;
}

export interface AgentState {
  agent_id: string;
  last_action: string | null;
  actions_today: number;
  assigned_tickets: string[];
  current_workload: number;
  is_overloaded: boolean;
  recent_rejections: number;
  recent_completions: number;
}

export interface RecentAction {
  agent_id: string;
  agent_name: string;
  action_type: string;
  ticket_key: string | null;
  scenario_id: string | null;
  timestamp: string;
  details: string | null;
}

export interface ScenarioDistribution {
  normal_flow: number;
  blocker: number;
  rework: number;
  scope_creep: number;
  dependency: number;
}

export interface ActiveScenario {
  scenario_id: string;
  ticket_key: string;
  scenario_type: 'normal_flow' | 'blocker' | 'rework' | 'scope_creep' | 'dependency';
  complexity: 'bug' | 'story' | 'feature';
  started: string;
  target_completion: string;
  current_phase: string;
  phase_started: string;
  phase_target_end: string;
  assigned_agent: string | null;
  involved_agents: string[];
  blocker_reason: string | null;
  rejection_reason: string | null;
  dependency_ticket: string | null;
  dependency_team: string | null;
  actions_taken: Array<{
    action_type: string;
    agent_id: string;
    timestamp: string;
    details: string | null;
  }>;
  comments_added: number;
  times_rejected: number;
}

export interface SimulationState {
  last_run: string | null;
  simulation_day: number;
  sprint: SprintState;
  jira_sprint?: JiraSprint;  // Real sprint data from Jira
  active_scenarios: Record<string, ActiveScenario>;
  completed_scenarios: string[];
  agents: Record<string, AgentState>;
  scenario_distribution: ScenarioDistribution;
  recent_actions: RecentAction[];
  recent_narrative: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  team: 'alpha' | 'beta';
  role: 'pm' | 'developer' | 'qa' | 'tech_lead';
  assigned_tickets: string[];
  current_workload: number;
  daily_actions: number;
}

export interface ScheduleInfo {
  days: number[];           // 1=Monday, 7=Sunday
  start_hour: number;
  end_hour: number;
}

export interface AgentsResponse {
  agents: AgentInfo[];
  last_run: string | null;
  schedule: ScheduleInfo;
}

export interface ScenariosResponse {
  active_count: number;
  scenarios: Array<{
    id: string;
    ticket_key: string;
    scenario_type: string;
    current_phase: string;
    assigned_agent: string | null;
    complexity: string;
    is_blocked: boolean;
    blocker_reason: string | null;
    is_rejected: boolean;
    rejection_reason: string | null;
    rework_count: number;
    started_at: string | null;
    target_end: string | null;
  }>;
  distribution: ScenarioDistribution;
}

export interface TriggerResponse {
  success: boolean;
  actions_taken: number;
  actions_planned: number;
  intensity: 'light' | 'normal' | 'busy';
  analysis_summary: Record<string, unknown>;
  planning_reasoning: string | null;
  actions: Array<Record<string, unknown>>;
  errors: Array<Record<string, unknown>>;
  active_scenarios: number;
  simulation_day: number;
  sprint: string;
  tick_start: string;
  tick_end: string;
}

export interface SessionSummary {
  session_id: string;
  started_at: string;
  ended_at: string | null;
  intensity: 'light' | 'normal' | 'busy';
  simulation_day: number;
  sprint_day: number;
  llm_calls: number;
  jira_calls: number;
  actions_planned: number;
  actions_completed: number;
  errors: number;
  total_input_tokens: number;
  total_output_tokens: number;
  success: boolean;
}

export interface SessionsResponse {
  sessions: SessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface TokenStats {
  total_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  avg_duration_ms: number;
  complex_calls: number;
  routine_calls: number;
}

// Sprint data from Jira
export interface SprintDataResponse {
  statusBreakdown: {
    backlog: number;
    inProgress: number;
    codeReview: number;
    testing: number;
    done: number;
  };
  burndownData: Array<{
    day: string;
    ideal: number;
    actual: number | null;
  }>;
  velocityData: Array<{
    sprintNumber: number;
    sprintName: string;
    completedItems: number;
  }>;
  sprint: JiraSprint;
  error?: string;
}

// Chat types
export interface ChatRequest {
  pm_id: string;
  message: string;
}

export interface ChatResponse {
  pm_id: string;
  pm_name: string;
  response: string;
  tickets_mentioned: string[];
}

// API Error class
export class ApiError extends Error {
  status: number;
  data?: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

// Generic fetch wrapper with error handling
async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      throw new ApiError(
        errorData?.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData
      );
    }

    return response.json();
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    // Network or other error
    throw new ApiError(
      error instanceof Error ? error.message : 'Network error',
      0
    );
  }
}

// API Methods
export const api = {
  // Health check
  health: () => fetchApi<HealthResponse>('/health'),

  // Get current simulation state
  getState: () => fetchApi<SimulationState>('/state'),

  // Get all agents
  getAgents: () => fetchApi<AgentsResponse>('/agents'),

  // Get active scenarios
  getScenarios: () => fetchApi<ScenariosResponse>('/scenarios'),

  // Get sprint data from Jira (status breakdown, burndown, velocity)
  getSprintData: () => fetchApi<SprintDataResponse>('/api/sprint-data'),

  // Trigger a simulation tick
  trigger: () => fetchApi<TriggerResponse>('/trigger', { method: 'POST' }),

  // Reset simulation state
  reset: () => fetchApi<{ message: string }>('/reset', { method: 'POST' }),

  // Force sprint planning
  planSprint: () =>
    fetchApi<{
      success: boolean;
      sprint: string;
      unassigned_items_available: number;
      result: Record<string, unknown>;
      error: string | null;
    }>('/plan-sprint', { method: 'POST' }),

  // Logging endpoints
  logs: {
    // Get recent sessions
    getSessions: (params?: {
      limit?: number;
      offset?: number;
      start_date?: string;
      end_date?: string;
    }) => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set('limit', String(params.limit));
      if (params?.offset) searchParams.set('offset', String(params.offset));
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      const query = searchParams.toString();
      return fetchApi<SessionsResponse>(`/logs/sessions${query ? `?${query}` : ''}`);
    },

    // Get token usage stats
    getStats: (params?: { start_date?: string; end_date?: string }) => {
      const searchParams = new URLSearchParams();
      if (params?.start_date) searchParams.set('start_date', params.start_date);
      if (params?.end_date) searchParams.set('end_date', params.end_date);
      const query = searchParams.toString();
      return fetchApi<TokenStats>(`/logs/stats${query ? `?${query}` : ''}`);
    },
  },

  // Chat with PM
  chat: (request: ChatRequest) =>
    fetchApi<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify(request),
    }),
};

export default api;
