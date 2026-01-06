import { useState, useEffect, useCallback, useRef } from 'react';
import api, {
  type SimulationState,
  type AgentsResponse,
  type ScenariosResponse,
  type HealthResponse,
  type SessionsResponse,
  type TokenStats,
  type SprintDataResponse,
  type VersionsResponse,
  type VersionProgress,
  type VersionIssuesResponse,
  type ReleaseNotesResponse,
  type ReleaseNotesHistoryItem,
  type OutputFormat,
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
  key?: string | number | null; // Force refetch when this changes
  onSuccess?: (data: unknown) => void;
  onError?: (error: ApiError) => void;
}

// Generic hook for API queries with polling support
function useQuery<T>(
  queryFn: () => Promise<T>,
  options: UseQueryOptions = {}
): UseQueryResult<T> {
  const { enabled = true, refetchInterval, key, onSuccess, onError } = options;
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
  }, [enabled, key]);

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

export function useSprintData(options?: UseQueryOptions) {
  return useQuery<SprintDataResponse>(() => api.getSprintData(), options);
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
  sprintData: SprintDataResponse | null;
}

export function useDashboardData(options?: { refetchInterval?: number }) {
  const { refetchInterval = 15000 } = options || {}; // Default 15 second refresh

  const health = useHealth({ refetchInterval });
  const state = useSimulationState({ refetchInterval });
  const agents = useAgents({ refetchInterval });
  const scenarios = useScenarios({ refetchInterval });
  const sprintData = useSprintData({ refetchInterval });

  const isLoading =
    health.isLoading || state.isLoading || agents.isLoading || scenarios.isLoading || sprintData.isLoading;

  const error = health.error || state.error || agents.error || scenarios.error || sprintData.error;

  // Store refetch functions in refs to avoid dependency changes
  const healthRefetchRef = useRef(health.refetch);
  healthRefetchRef.current = health.refetch;
  const stateRefetchRef = useRef(state.refetch);
  stateRefetchRef.current = state.refetch;
  const agentsRefetchRef = useRef(agents.refetch);
  agentsRefetchRef.current = agents.refetch;
  const scenariosRefetchRef = useRef(scenarios.refetch);
  scenariosRefetchRef.current = scenarios.refetch;
  const sprintDataRefetchRef = useRef(sprintData.refetch);
  sprintDataRefetchRef.current = sprintData.refetch;

  const refetch = useCallback(async () => {
    await Promise.all([
      healthRefetchRef.current(),
      stateRefetchRef.current(),
      agentsRefetchRef.current(),
      scenariosRefetchRef.current(),
      sprintDataRefetchRef.current(),
    ]);
  }, []);

  return {
    data: {
      health: health.data,
      state: state.data,
      agents: agents.data,
      scenarios: scenarios.data,
      sprintData: sprintData.data,
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

// =============================================================================
// Release/Version Hooks
// =============================================================================

// Hook for versions list
export function useVersions(
  params?: { released?: boolean; includeArchived?: boolean },
  options?: UseQueryOptions
) {
  return useQuery<VersionsResponse>(
    () => api.releases.getVersions(params),
    options
  );
}

// Hook for version progress
export function useVersionProgress(
  versionName: string | null,
  options?: UseQueryOptions
) {
  return useQuery<VersionProgress>(
    () => api.releases.getVersionProgress(versionName!),
    {
      ...options,
      enabled: !!versionName && (options?.enabled !== false),
      key: versionName, // Force refetch when version changes
    }
  );
}

// Hook for version issues
export function useVersionIssues(
  versionName: string | null,
  options?: UseQueryOptions
) {
  return useQuery<VersionIssuesResponse>(
    () => api.releases.getVersionIssues(versionName!),
    {
      ...options,
      enabled: !!versionName && (options?.enabled !== false),
      key: versionName, // Force refetch when version changes
    }
  );
}

// Mutation hook for generating release notes
export function useGenerateReleaseNotes() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const generate = useCallback(async (
    versionName: string,
    format: OutputFormat = 'md',
    regenerate: boolean = false
  ): Promise<ReleaseNotesResponse | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await api.releases.generateNotes(versionName, format, regenerate);

      // Handle file download for binary formats
      if (result instanceof Blob) {
        const url = window.URL.createObjectURL(result);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${versionName}_release_notes.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        return null;
      }

      return result;
    } catch (err) {
      const apiError = err instanceof ApiError
        ? err
        : new ApiError(err instanceof Error ? err.message : 'Unknown error', 0);
      setError(apiError);
      throw apiError;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { generate, isLoading, error };
}

// Hook for release notes history
export function useReleaseNotesHistory(options?: UseQueryOptions) {
  return useQuery<ReleaseNotesHistoryItem[]>(
    () => api.releases.getHistory(),
    options
  );
}

// Mutation hook for downloading release notes
export function useDownloadReleaseNotes() {
  const [isDownloading, setIsDownloading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const download = useCallback(async (
    versionName: string,
    format: OutputFormat
  ): Promise<void> => {
    setIsDownloading(true);
    setError(null);
    try {
      await api.releases.downloadNotes(versionName, format);
    } catch (err) {
      const apiError = err instanceof ApiError
        ? err
        : new ApiError(err instanceof Error ? err.message : 'Download failed', 0);
      setError(apiError);
      throw apiError;
    } finally {
      setIsDownloading(false);
    }
  }, []);

  return { download, isDownloading, error };
}
