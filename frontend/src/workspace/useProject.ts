import { useCallback, useEffect, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import {
  createEnvironment as createEnvironmentRequest,
  createFlag as createFlagRequest,
  evaluateFlag as evaluateFlagRequest,
  fetchFlags,
  fetchProjectEnvironments,
  getErrorMessage,
  updateFlagEnvState,
} from '../api';
import type { Environment, EvaluateResult, Flag, FlagState } from '../api';

export interface PlaygroundState {
  userId: string;
  result?: EvaluateResult;
  evaluating?: boolean;
}

export interface ProjectData {
  flags: Flag[];
  environments: Environment[];
  activeEnv: string;
  loading: boolean;
  error: string | null;
  playground: Record<string, PlaygroundState>;
  setActiveEnv: (environment: string) => void;
  refresh: () => Promise<void>;
  toggleKillSwitch: (flag: Flag) => Promise<void>;
  updateRollout: (flag: Flag, percentage: number) => Promise<void>;
  createFlag: (data: {
    key: string;
    name: string;
    description?: string;
    default_value: boolean;
  }) => Promise<Flag>;
  createEnvironment: (name: string) => Promise<Environment>;
  evaluate: (flagKey: string, userId?: string) => Promise<void>;
  stateFor: (flag: Flag, environment?: string) => FlagState;
}

const FALLBACK_STATE: FlagState = {
  env: 'dev',
  enabled: true,
  percentage: 0,
  version: 1,
};

export function useProject(projectId: string | undefined): ProjectData {
  const [flags, setFlags] = useState<Flag[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [activeEnv, setActiveEnv] = useState('dev');
  const [loading, setLoading] = useState(Boolean(projectId));
  const [error, setError] = useState<string | null>(null);
  const [playground, setPlayground] = useState<Record<string, PlaygroundState>>({});
  const requestSequence = useRef(0);

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    if (!projectId) {
      setFlags([]);
      setEnvironments([]);
      setLoading(false);
      return;
    }
    try {
      const [nextFlags, nextEnvironments] = await Promise.all([
        fetchFlags(projectId),
        fetchProjectEnvironments(projectId),
      ]);
      if (sequence !== requestSequence.current) return;
      setFlags(nextFlags);
      setEnvironments(nextEnvironments);
      setError(null);
      setActiveEnv((previous) => {
        if (nextEnvironments.some((environment) => environment.name === previous)) return previous;
        return nextEnvironments[0]?.name ?? 'dev';
      });
    } catch (requestError) {
      if (sequence !== requestSequence.current) return;
      setError(getErrorMessage(requestError, 'Failed to load project data'));
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    const resetTimer = window.setTimeout(() => {
      requestSequence.current += 1;
      setFlags([]);
      setEnvironments([]);
      setPlayground({});
      setError(null);
      setLoading(Boolean(projectId));
      void load();
    }, 0);
    const interval = projectId ? window.setInterval(() => void load(), 5000) : undefined;
    return () => {
      window.clearTimeout(resetTimer);
      requestSequence.current += 1;
      if (interval !== undefined) window.clearInterval(interval);
    };
  }, [load, projectId]);

  const refresh = useCallback(async () => {
    await load();
  }, [load]);

  const toggleKillSwitch = useCallback(
    async (flag: Flag) => {
      if (!projectId) return;
      const current = flag.states.find((state) => state.env === activeEnv) ?? FALLBACK_STATE;
      try {
        await updateFlagEnvState(projectId, flag.key, activeEnv, { enabled: !current.enabled });
        await load();
      } catch (requestError) {
        setError(getErrorMessage(requestError, 'Error updating kill switch'));
      }
    },
    [activeEnv, load, projectId],
  );

  const updateRollout = useCallback(
    async (flag: Flag, percentage: number) => {
      if (!projectId) return;
      try {
        await updateFlagEnvState(projectId, flag.key, activeEnv, { percentage });
        setFlags((previous) =>
          previous.map((currentFlag) => {
            if (currentFlag.id !== flag.id) return currentFlag;
            const existing = currentFlag.states.some((state) => state.env === activeEnv);
            return {
              ...currentFlag,
              states: existing
                ? currentFlag.states.map((state) =>
                    state.env === activeEnv ? { ...state, percentage } : state,
                  )
                : [...currentFlag.states, { ...FALLBACK_STATE, env: activeEnv, percentage }],
            };
          }),
        );
      } catch (requestError) {
        setError(getErrorMessage(requestError, 'Error updating rollout'));
      }
    },
    [activeEnv, projectId],
  );

  const createFlag = useCallback(
    async (data: {
      key: string;
      name: string;
      description?: string;
      default_value: boolean;
    }) => {
      if (!projectId) throw new Error('Project is not available');
      const created = await createFlagRequest(projectId, data);
      await load();
      return created;
    },
    [load, projectId],
  );

  const createEnvironment = useCallback(
    async (name: string) => {
      if (!projectId) throw new Error('Project is not available');
      const created = await createEnvironmentRequest(projectId, name);
      await load();
      setActiveEnv(created.name);
      return created;
    },
    [load, projectId],
  );

  const evaluate = useCallback(
    async (flagKey: string, requestedUserId?: string) => {
      if (!projectId) return;
      const state = playground[flagKey] ?? { userId: requestedUserId || 'user_123' };
      const userId = requestedUserId || state.userId || 'user_123';
      setPlayground((previous) => ({
        ...previous,
        [flagKey]: { userId, evaluating: true },
      }));
      try {
        const result = await evaluateFlagRequest({
          projectId,
          flag_key: flagKey,
          env: activeEnv,
          user_id: userId,
        });
        setPlayground((previous) => ({
          ...previous,
          [flagKey]: { userId, result, evaluating: false },
        }));
      } catch (requestError) {
        setPlayground((previous) => ({
          ...previous,
          [flagKey]: { ...state, userId, evaluating: false },
        }));
        setError(getErrorMessage(requestError, 'Error evaluating flag'));
      }
    },
    [activeEnv, playground, projectId],
  );

  const stateFor = useCallback(
    (flag: Flag, environment = activeEnv): FlagState =>
      flag.states.find((state) => state.env === environment) ?? {
        ...FALLBACK_STATE,
        env: environment,
      },
    [activeEnv],
  );

  return {
    flags,
    environments,
    activeEnv,
    loading,
    error,
    playground,
    setActiveEnv,
    refresh,
    toggleKillSwitch,
    updateRollout,
    createFlag,
    createEnvironment,
    evaluate,
    stateFor,
  };
}

export interface ProjectOutletContext {
  projectData: ProjectData;
}

export function useProjectData(): ProjectData {
  return useOutletContext<ProjectOutletContext>().projectData;
}
