import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { asBool } from '@/lib/utils';
import type { AgentBackend } from '@/lib/api/types';

export type SettingsFormState = {
  attached_launcher: string;
  default_base_branch: string;
  worktree_base_ref_strategy: string;
  auto_review: boolean;
  open_last_project_on_startup: boolean;
  auto_init_git_repo: boolean;
  auto_init_git_initial_commit: boolean;
  require_review_approval: boolean;
  serialize_merges: boolean;
  skip_attached_instructions_popup: boolean;
  git_user_mode: string;
  git_user_name: string;
  git_user_email: string;
  default_agent_backend: string;
  default_model_claude: string;
  default_model_openai: string;
  additional_instructions: string;
  review_strictness: string;
  planning_depth: string;
  auto_confirm_single_tasks: boolean;
  use_recommended_backend: boolean;
};

export const DEFAULT_FORM: SettingsFormState = {
  attached_launcher: 'tmux',
  default_base_branch: 'main',
  worktree_base_ref_strategy: 'local_if_ahead',
  auto_review: true,
  open_last_project_on_startup: false,
  auto_init_git_repo: true,
  auto_init_git_initial_commit: true,
  require_review_approval: false,
  serialize_merges: false,
  skip_attached_instructions_popup: false,
  git_user_mode: 'kagan_agent',
  git_user_name: '',
  git_user_email: '',
  default_agent_backend: 'claude-code',
  default_model_claude: '',
  default_model_openai: '',
  additional_instructions: '',
  review_strictness: 'balanced',
  planning_depth: 'always',
  auto_confirm_single_tasks: false,
  use_recommended_backend: false,
};

export interface UseSettingsFormResult {
  form: SettingsFormState;
  savedRef: React.MutableRefObject<SettingsFormState>;
  resolvedGit: { name: string; email: string };
  dotfileOverrides: Record<string, string | null>;
  loading: boolean;
  availableBackends: AgentBackend[];
  setField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
  saveField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => Promise<void>;
  onGitUserModeChange: (mode: string) => Promise<void>;
}

export function useSettingsForm(): UseSettingsFormResult {
  const [form, setForm] = useState<SettingsFormState>(DEFAULT_FORM);
  const savedRef = useRef<SettingsFormState>(DEFAULT_FORM);
  const [resolvedGit, setResolvedGit] = useState<{ name: string; email: string }>({
    name: '',
    email: '',
  });
  const [dotfileOverrides, setDotfileOverrides] = useState<Record<string, string | null>>({});
  const [loading, setLoading] = useState(true);
  const [availableBackends, setAvailableBackends] = useState<AgentBackend[]>([]);

  const setField = <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const saveField = async <K extends keyof SettingsFormState>(
    key: K,
    value: SettingsFormState[K],
  ) => {
    setField(key, value);
    try {
      const apiValue = typeof value === 'boolean' ? String(value) : (value as string);
      const payload: Record<string, string> = { [key]: apiValue };
      await apiClient.setSettings(payload);
      savedRef.current = { ...savedRef.current, [key]: value };
      toast.success('Updated', { duration: 1500 });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to save');
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const [settings, resolved, agents] = await Promise.all([
          apiClient.getSettings(),
          apiClient.getResolvedSettings(),
          apiClient.getChatAgents(),
        ]);

        setAvailableBackends(agents.backends);
        setResolvedGit({
          name: resolved.git_user_name || '',
          email: resolved.git_user_email || '',
        });
        setDotfileOverrides(resolved.dotfile_overrides || {});

        const loaded: SettingsFormState = {
          attached_launcher: settings.attached_launcher || DEFAULT_FORM.attached_launcher,
          default_base_branch: settings.default_base_branch || DEFAULT_FORM.default_base_branch,
          worktree_base_ref_strategy:
            settings.worktree_base_ref_strategy || DEFAULT_FORM.worktree_base_ref_strategy,
          auto_review: asBool(settings.auto_review, DEFAULT_FORM.auto_review),
          open_last_project_on_startup: asBool(
            settings.open_last_project_on_startup,
            DEFAULT_FORM.open_last_project_on_startup,
          ),
          auto_init_git_repo: asBool(settings.auto_init_git_repo, DEFAULT_FORM.auto_init_git_repo),
          auto_init_git_initial_commit: asBool(
            settings.auto_init_git_initial_commit,
            DEFAULT_FORM.auto_init_git_initial_commit,
          ),
          require_review_approval: asBool(
            settings.require_review_approval,
            DEFAULT_FORM.require_review_approval,
          ),
          serialize_merges: asBool(settings.serialize_merges, DEFAULT_FORM.serialize_merges),
          skip_attached_instructions_popup: asBool(
            settings.skip_attached_instructions_popup,
            DEFAULT_FORM.skip_attached_instructions_popup,
          ),
          git_user_mode: settings.git_user_mode || DEFAULT_FORM.git_user_mode,
          git_user_name: settings.git_user_name || resolved.git_user_name || '',
          git_user_email: settings.git_user_email || resolved.git_user_email || '',
          default_agent_backend:
            settings.default_agent_backend ||
            agents.default ||
            DEFAULT_FORM.default_agent_backend,
          default_model_claude: settings.default_model_claude || '',
          default_model_openai: settings.default_model_openai || '',
          additional_instructions: settings.additional_instructions || '',
          review_strictness: settings.review_strictness || DEFAULT_FORM.review_strictness,
          planning_depth: settings.planning_depth || DEFAULT_FORM.planning_depth,
          auto_confirm_single_tasks: asBool(
            settings.auto_confirm_single_tasks,
            DEFAULT_FORM.auto_confirm_single_tasks,
          ),
          use_recommended_backend: asBool(
            settings.use_recommended_backend,
            DEFAULT_FORM.use_recommended_backend,
          ),
        };
        setForm(loaded);
        savedRef.current = loaded;
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to load settings');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const onGitUserModeChange = async (mode: string) => {
    await saveField('git_user_mode', mode);
    try {
      const resolved = await apiClient.getResolvedSettings();
      setResolvedGit({
        name: resolved.git_user_name || '',
        email: resolved.git_user_email || '',
      });
      if (mode !== 'custom') {
        const gitName = resolved.git_user_name || '';
        const gitEmail = resolved.git_user_email || '';
        setForm((prev) => ({ ...prev, git_user_name: gitName, git_user_email: gitEmail }));
        savedRef.current = {
          ...savedRef.current,
          git_user_name: gitName,
          git_user_email: gitEmail,
        };
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to refresh resolved identity');
    }
  };

  return {
    form,
    savedRef,
    resolvedGit,
    dotfileOverrides,
    loading,
    availableBackends,
    setField,
    saveField,
    onGitUserModeChange,
  };
}
