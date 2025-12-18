import { useState, useEffect, useCallback, useRef } from 'react';
import api, {
  type SimulationState,
  type AgentsResponse,
  type ScenariosResponse,
  type HealthResponse,
  type SessionsResponse,
  type TokenStats,
  ApiError,
} from '@/lib/api';

interface UseQueryResult<T> {
  data: T | null;
  isLoading: boolean;
  error: ApiError | null;
  refetch: () => Promise<void>;
}

interface UseQueryOptions {
  enabled?: boolean;
  refetchInterval?: number; // in milliseconds
  onSuccess?: (data: unknown) => void;
  onError?: (error: ApiError) => void;
}

// Generic hook for API queries with polling support
function useQuery<T>(
  queryFn: () => Promise<T>,
  options: UseQueryOptions = {}
): UseQueryResult<T> {
  const { enabled = true, refetchInterval, onSuccess, onError } = options;
  const [data, setData] = useState<T | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const mountedRef = useRef(true);

  // Store queryFn in a ref to avoid infinite loops
  // The queryFn is stable (always calls the same API) but creates new references on each render
  const queryFnRef = useRef(queryFn);
  queryFnRef.current = queryFn;

  // Store callbacks in refs to avoid them being dependencies
  const onSuccessRef = useRef(onSuccess);
  onSuccessRef.current = onSuccess;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const fetchData = useCallback(async () => {
    if (!enabled) return;

    try {
      setIsLoading(true);
      const result = await queryFnRef.current();
      if (mountedRef.current) {
        setData(result);
        setError(null);
        onSuccessRef.current?.(result);
      }
    } catch (err) {
      if (mountedRef.current) {
        const apiError =
          err instanceof ApiError
            ? err
            : new ApiError(err instanceof Error ? err.message : 'Unknown error', 0);
        setError(apiError);
        onErrorRef.current?.(apiError);
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [enabled]);

  useEffect(() => {
    mountedRef.current = true;
    fetchData();

    return () => {
      mountedRef.current = false;
    };
  }, [fetchData]);

  // Set up polling if refetchInterval is provided
  useEffect(() => {
    if (!refetchInterval || !enabled) return;

    const interval = setInterval(fetchData, refetchInterval);
    return () => clearInterval(interval);
  }, [refetchInterval, enabled, fetchData]);

  return { data, isLoading, error, refetch: fetchData };
}

// Specific hooks for each API endpoint

export function useHealth(options?: UseQueryOptions) {
  return useQuery<HealthResponse>(() => api.health(), options);
}

export function useSimulationState(options?: UseQueryOptions) {
  return useQuery<SimulationState>(() => api.getState(), options);
}

export function useAgents(options?: UseQueryOptions) {
  return useQuery<AgentsResponse>(() => api.getAgents(), options);
}

export function useScenarios(options?: UseQueryOptions) {
  return useQuery<ScenariosResponse>(() => api.getScenarios(), options);
}

export function useSessions(
  params?: { limit?: number; offset?: number },
  options?: UseQueryOptions
) {
  return useQuery<SessionsResponse>(
    () => api.logs.getSessions(params),
    options
  );
}

export function useTokenStats(options?: UseQueryOptions) {
  return useQuery<TokenStats>(() => api.logs.getStats(), options);
}

// Combined dashboard data hook
export interface DashboardData {
  health: HealthResponse | null;
  state: SimulationState | null;
  agents: AgentsResponse | null;
  scenarios: ScenariosResponse | null;
}

export function useDashboardData(options?: { refetchInterval?: number }) {
  const { refetchInterval = 15000 } = options || {}; // Default 15 second refresh

  const health = useHealth({ refetchInterval });
  const state = useSimulationState({ refetchInterval });
  const agents = useAgents({ refetchInterval });
  const scenarios = useScenarios({ refetchInterval });

  const isLoading =
    health.isLoading || state.isLoading || agents.isLoading || scenarios.isLoading;

  const error = health.error || state.error || agents.error || scenarios.error;

  // Store refetch functions in refs to avoid dependency changes
  const healthRefetchRef = useRef(health.refetch);
  healthRefetchRef.current = health.refetch;
  const stateRefetchRef = useRef(state.refetch);
  stateRefetchRef.current = state.refetch;
  const agentsRefetchRef = useRef(agents.refetch);
  agentsRefetchRef.current = agents.refetch;
  const scenariosRefetchRef = useRef(scenarios.refetch);
  scenariosRefetchRef.current = scenarios.refetch;

  const refetch = useCallback(async () => {
    await Promise.all([
      healthRefetchRef.current(),
      stateRefetchRef.current(),
      agentsRefetchRef.current(),
      scenariosRefetchRef.current(),
    ]);
  }, []);

  return {
    data: {
      health: health.data,
      state: state.data,
      agents: agents.data,
      scenarios: scenarios.data,
    },
    isLoading,
    error,
    refetch,
  };
}

// Mutation hook for trigger action
export function useTriggerMutation() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const trigger = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await api.trigger();
      return result;
    } catch (err) {
      const apiError =
        err instanceof ApiError
          ? err
          : new ApiError(err instanceof Error ? err.message : 'Unknown error', 0);
      setError(apiError);
      throw apiError;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { trigger, isLoading, error };
}

// Mutation hook for reset
export function useResetMutation() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const reset = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await api.reset();
      return result;
    } catch (err) {
      const apiError =
        err instanceof ApiError
          ? err
          : new ApiError(err instanceof Error ? err.message : 'Unknown error', 0);
      setError(apiError);
      throw apiError;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { reset, isLoading, error };
}
