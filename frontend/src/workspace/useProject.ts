import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import {
  createEnvironment as createEnvironmentRequest,
  createFlag as createFlagRequest,
  createFlagRule as createFlagRuleRequest,
  deleteFlagRule as deleteFlagRuleRequest,
  evaluateFlag as evaluateFlagRequest,
  fetchFlags,
  fetchProjectEnvironments,
  getErrorMessage,
  reorderFlagRules as reorderFlagRulesRequest,
  updateFlagEnvState,
  updateFlagRule as updateFlagRuleRequest,
  updateFlag as updateFlagRequest,
} from '../api';
import type {
  Environment,
  EvaluateResult,
  Flag,
  FlagState,
  RuleCondition,
  TargetingRule,
} from '../api';

export interface PlaygroundState {
  userId: string;
  attributes?: Record<string, unknown>;
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
  updateDefaultValue: (flag: Flag, defaultValue: boolean) => Promise<void>;
  createFlag: (data: {
    key: string;
    name: string;
    description?: string;
    default_value: boolean;
  }) => Promise<Flag>;
  createEnvironment: (name: string) => Promise<Environment>;
  createRule: (
    flag: Flag,
    data: { conditions: RuleCondition[]; serve: boolean },
  ) => Promise<TargetingRule>;
  updateRule: (
    flag: Flag,
    rule: TargetingRule,
    data: { conditions?: RuleCondition[]; serve?: boolean },
  ) => Promise<TargetingRule>;
  deleteRule: (flag: Flag, rule: TargetingRule) => Promise<void>;
  moveRule: (flag: Flag, rule: TargetingRule, direction: -1 | 1) => Promise<void>;
  evaluate: (
    flagKey: string,
    userId?: string,
    attributes?: Record<string, unknown>,
  ) => Promise<void>;
  setPlaygroundAttributes: (flagKey: string, attributes: Record<string, unknown>) => void;
  stateFor: (flag: Flag, environment?: string) => FlagState;
  rulesFor: (flag: Flag, environment?: string) => TargetingRule[];
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
  // Guards optimistic rollout writes against out-of-order responses.
  const rolloutSequences = useRef(new Map<string, number>());

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
      // The value is shown before the server confirms it, so a slow response
      // must not overwrite a newer edit that is already on screen. Each
      // (flag, environment) pair keeps its own sequence number.
      const key = `${flag.id}:${activeEnv}`;
      const sequence = (rolloutSequences.current.get(key) ?? 0) + 1;
      rolloutSequences.current.set(key, sequence);

      const applyPercentage = (value: number) => {
        setFlags((previous) =>
          previous.map((currentFlag) => {
            if (currentFlag.id !== flag.id) return currentFlag;
            const existing = currentFlag.states.some((state) => state.env === activeEnv);
            return {
              ...currentFlag,
              states: existing
                ? currentFlag.states.map((state) =>
                    state.env === activeEnv ? { ...state, percentage: value } : state,
                  )
                : [...currentFlag.states, { ...FALLBACK_STATE, env: activeEnv, percentage: value }],
            };
          }),
        );
      };

      applyPercentage(percentage);

      try {
        await updateFlagEnvState(projectId, flag.key, activeEnv, { percentage });
        if ((rolloutSequences.current.get(key) ?? 0) !== sequence) return;
      } catch (requestError) {
        if ((rolloutSequences.current.get(key) ?? 0) !== sequence) return;
        setError(getErrorMessage(requestError, 'Error updating rollout'));
        // Drop the sequence so the next poll is free to reconcile the slider.
        rolloutSequences.current.delete(key);
        await load();
      }
    },
    [activeEnv, load, projectId],
  );

  const updateDefaultValue = useCallback(
    async (flag: Flag, defaultValue: boolean) => {
      if (!projectId) return;
      try {
        await updateFlagRequest(projectId, flag.key, { default_value: defaultValue });
        await load();
      } catch (requestError) {
        setError(getErrorMessage(requestError, 'Error updating default value'));
      }
    },
    [load, projectId],
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
    async (flagKey: string, requestedUserId?: string, requestedAttributes?: Record<string, unknown>) => {
      if (!projectId) return;
      const state = playground[flagKey];
      const userId = requestedUserId || state?.userId || 'user_123';
      const attributes = requestedAttributes ?? state?.attributes;
      setPlayground((previous) => ({
        ...previous,
        [flagKey]: { userId, attributes, evaluating: true },
      }));
      try {
        const result = await evaluateFlagRequest({
          projectId,
          flag_key: flagKey,
          env: activeEnv,
          user_id: userId,
          attributes,
        });
        setPlayground((previous) => ({
          ...previous,
          [flagKey]: { userId, attributes, result, evaluating: false },
        }));
      } catch (requestError) {
        setPlayground((previous) => ({
          ...previous,
          [flagKey]: { ...(previous[flagKey] ?? { userId }), userId, attributes, evaluating: false },
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

  // Kept in workspace state (not local component state) so the rule builder can
  // preview conditions against the same context the playground will send.
  const setPlaygroundAttributes = useCallback(
    (flagKey: string, attributes: Record<string, unknown>) => {
      setPlayground((previous) => ({
        ...previous,
        [flagKey]: { userId: previous[flagKey]?.userId ?? 'user_123', attributes },
      }));
    },
    [],
  );

  const rulesFor = useCallback(
    (flag: Flag, environment = activeEnv): TargetingRule[] =>
      (flag.rules ?? [])
        .filter((rule) => rule.env === environment)
        .sort((first, second) => first.priority - second.priority),
    [activeEnv],
  );

  const createRule = useCallback(
    async (flag: Flag, data: { conditions: RuleCondition[]; serve: boolean }) => {
      if (!projectId) throw new Error('Project is not available');
      const created = await createFlagRuleRequest(projectId, flag.key, activeEnv, data);
      await load();
      return created;
    },
    [activeEnv, load, projectId],
  );

  const updateRule = useCallback(
    async (
      flag: Flag,
      rule: TargetingRule,
      data: { conditions?: RuleCondition[]; serve?: boolean },
    ) => {
      if (!projectId) throw new Error('Project is not available');
      const updated = await updateFlagRuleRequest(projectId, flag.key, activeEnv, rule.id, data);
      await load();
      return updated;
    },
    [activeEnv, load, projectId],
  );

  const deleteRule = useCallback(
    async (flag: Flag, rule: TargetingRule) => {
      if (!projectId) throw new Error('Project is not available');
      await deleteFlagRuleRequest(projectId, flag.key, activeEnv, rule.id);
      await load();
    },
    [activeEnv, load, projectId],
  );

  const moveRule = useCallback(
    async (flag: Flag, rule: TargetingRule, direction: -1 | 1) => {
      if (!projectId) return;
      // The API requires the complete ordering, so derive it from the current
      // environment rules rather than patching a single priority in place.
      const ordered = rulesFor(flag);
      const index = ordered.findIndex((candidate) => candidate.id === rule.id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= ordered.length) return;
      const next = [...ordered];
      [next[index], next[target]] = [next[target], next[index]];
      try {
        await reorderFlagRulesRequest(
          projectId,
          flag.key,
          activeEnv,
          next.map((candidate) => candidate.id),
        );
        await load();
      } catch (requestError) {
        setError(getErrorMessage(requestError, 'Error re-ordering targeting rules'));
      }
    },
    [activeEnv, load, projectId, rulesFor],
  );

  return useMemo(
    () => ({
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
      updateDefaultValue,
      createFlag,
      createEnvironment,
      createRule,
      updateRule,
      deleteRule,
      moveRule,
      evaluate,
      setPlaygroundAttributes,
      stateFor,
      rulesFor,
    }),
    [
      flags,
      environments,
      activeEnv,
      loading,
      error,
      playground,
      refresh,
      toggleKillSwitch,
      updateRollout,
      updateDefaultValue,
      createFlag,
      createEnvironment,
      createRule,
      updateRule,
      deleteRule,
      moveRule,
      evaluate,
      setPlaygroundAttributes,
      stateFor,
      rulesFor,
    ],
  );
}

export interface ProjectOutletContext {
  projectData: ProjectData;
}

export function useProjectData(): ProjectData {
  return useOutletContext<ProjectOutletContext>().projectData;
}
