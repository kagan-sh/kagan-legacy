import { useEffect, useRef, useState } from 'react';
import { useAtom, useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { themeModeAtom, setThemeModeAtom } from '@/lib/atoms/theme';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Switch } from '@/components/ui/switch';
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
} from '@/components/ui/field';
import { AppearanceSettings } from './sections/appearance-settings';
import { WorkflowSettings } from './sections/workflow-settings';
import { WorkspaceSettings } from './sections/workspace-settings';
import { OrchestrationSettings } from './sections/orchestration-settings';
import { AdditionalInstructionsSettings } from './sections/additional-instructions';

type ThemeMode = 'system' | 'dark' | 'light';

export type SettingsFormState = {
  pair_launcher: string;
  default_base_branch: string;
  worktree_base_ref_strategy: string;
  auto_review: boolean;
  open_last_project_on_startup: boolean;
  auto_init_git_repo: boolean;
  auto_init_git_initial_commit: boolean;
  require_review_approval: boolean;
  serialize_merges: boolean;
  skip_pair_instructions_popup: boolean;
  git_user_mode: string;
  git_user_name: string;
  git_user_email: string;
  default_agent_backend: string;
  default_model_claude: string;
  default_model_openai: string;
  additional_instructions: string;
  default_execution_mode: string;
  review_strictness: string;
  planning_depth: string;
  auto_confirm_single_tasks: boolean;
};

export const DEFAULT_FORM: SettingsFormState = {
  pair_launcher: 'tmux',
  default_base_branch: 'main',
  worktree_base_ref_strategy: 'local_if_ahead',
  auto_review: true,
  open_last_project_on_startup: false,
  auto_init_git_repo: true,
  auto_init_git_initial_commit: true,
  require_review_approval: false,
  serialize_merges: false,
  skip_pair_instructions_popup: false,
  git_user_mode: 'kagan_agent',
  git_user_name: '',
  git_user_email: '',
  default_agent_backend: 'claude-code',
  default_model_claude: '',
  default_model_openai: '',
  additional_instructions: '',
  default_execution_mode: 'ask',
  review_strictness: 'balanced',
  planning_depth: 'always',
  auto_confirm_single_tasks: false,
};

export function asBool(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined) return fallback;
  return !['0', 'false', 'no', 'off'].includes(value.trim().toLowerCase());
}

export interface ToggleRowProps {
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
}

export function ToggleRow({ title, description, checked, onCheckedChange }: ToggleRowProps) {
  return (
    <Field orientation="horizontal" className="py-3">
      <FieldContent>
        <FieldLabel>{title}</FieldLabel>
        <FieldDescription>{description}</FieldDescription>
      </FieldContent>
      <Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={title} />
    </Field>
  );
}

export function SettingsPanel() {
  const [themeMode] = useAtom(themeModeAtom);
  const setThemeMode = useSetAtom(setThemeModeAtom);

  const [form, setForm] = useState<SettingsFormState>(DEFAULT_FORM);
  const savedRef = useRef<SettingsFormState>(DEFAULT_FORM);
  const [resolvedGit, setResolvedGit] = useState<{ name: string; email: string }>({ name: '', email: '' });
  const [dotfileOverrides, setDotfileOverrides] = useState<Record<string, string | null>>({});

  const [loading, setLoading] = useState(true);
  const [availableBackends, setAvailableBackends] = useState<string[]>([]);

  const setField = <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  /** Save a single field atomically to the API. */
  const saveField = async <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => {
    setField(key, value);
    try {
      const apiValue = typeof value === 'boolean' ? String(value) : (value as string);
      const payload: Record<string, string> = { [key]: apiValue };
      if (key === 'default_agent_backend') payload.default_agent = apiValue;
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
          pair_launcher: settings.pair_launcher || DEFAULT_FORM.pair_launcher,
          default_base_branch: settings.default_base_branch || DEFAULT_FORM.default_base_branch,
          worktree_base_ref_strategy: settings.worktree_base_ref_strategy || DEFAULT_FORM.worktree_base_ref_strategy,
          auto_review: asBool(settings.auto_review, DEFAULT_FORM.auto_review),
          open_last_project_on_startup: asBool(settings.open_last_project_on_startup, DEFAULT_FORM.open_last_project_on_startup),
          auto_init_git_repo: asBool(settings.auto_init_git_repo, DEFAULT_FORM.auto_init_git_repo),
          auto_init_git_initial_commit: asBool(settings.auto_init_git_initial_commit, DEFAULT_FORM.auto_init_git_initial_commit),
          require_review_approval: asBool(settings.require_review_approval, DEFAULT_FORM.require_review_approval),
          serialize_merges: asBool(settings.serialize_merges, DEFAULT_FORM.serialize_merges),
          skip_pair_instructions_popup: asBool(settings.skip_pair_instructions_popup, DEFAULT_FORM.skip_pair_instructions_popup),
          git_user_mode: settings.git_user_mode || DEFAULT_FORM.git_user_mode,
          git_user_name: settings.git_user_name || resolved.git_user_name || '',
          git_user_email: settings.git_user_email || resolved.git_user_email || '',
          default_agent_backend: settings.default_agent_backend || settings.default_agent || agents.default || DEFAULT_FORM.default_agent_backend,
          default_model_claude: settings.default_model_claude || '',
          default_model_openai: settings.default_model_openai || '',
          additional_instructions: settings.additional_instructions || '',
          default_execution_mode: settings.default_execution_mode || DEFAULT_FORM.default_execution_mode,
          review_strictness: settings.review_strictness || DEFAULT_FORM.review_strictness,
          planning_depth: settings.planning_depth || DEFAULT_FORM.planning_depth,
          auto_confirm_single_tasks: asBool(settings.auto_confirm_single_tasks, DEFAULT_FORM.auto_confirm_single_tasks),
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
      setResolvedGit({ name: resolved.git_user_name || '', email: resolved.git_user_email || '' });
      if (mode !== 'custom') {
        const gitName = resolved.git_user_name || '';
        const gitEmail = resolved.git_user_email || '';
        setForm((prev) => ({ ...prev, git_user_name: gitName, git_user_email: gitEmail }));
        savedRef.current = { ...savedRef.current, git_user_name: gitName, git_user_email: gitEmail };
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to refresh resolved identity');
    }
  };

  return (
    <Card className="overflow-hidden p-0">

      {loading ? (
        <div className="space-y-3 px-5 py-5">
          <div className="h-14 animate-pulse bg-[var(--muted)]" />
          <div className="h-14 animate-pulse bg-[var(--muted)]" />
          <div className="h-14 animate-pulse bg-[var(--muted)]" />
        </div>
      ) : (
        <FieldGroup className="space-y-0 px-5 py-5">
          <OrchestrationSettings form={form} saveField={saveField} />

          <FieldSeparator />

          <AppearanceSettings
            form={form}
            setField={setField}
            saveField={saveField}
            themeMode={themeMode as ThemeMode}
            setThemeMode={(mode) => setThemeMode(mode)}
          />

          <FieldSeparator />

          <WorkflowSettings form={form} saveField={saveField} />

          <FieldSeparator />

          <WorkspaceSettings form={form} setField={setField} saveField={saveField} />

          <FieldSeparator />

          <FieldSet>
            <FieldLegend variant="label">Identity and Models</FieldLegend>
            <Field>
              <FieldLabel>Default agent backend</FieldLabel>
              <FieldDescription>Agent used for new tasks when none is specified.</FieldDescription>
              <NativeSelect
                value={form.default_agent_backend}
                onChange={(event) => saveField('default_agent_backend', event.target.value)}
              >
                {availableBackends.length > 0 ? (
                  availableBackends.map((backend) => (
                    <NativeSelectOption key={backend} value={backend}>{backend}</NativeSelectOption>
                  ))
                ) : (
                  <NativeSelectOption value={form.default_agent_backend}>{form.default_agent_backend}</NativeSelectOption>
                )}
              </NativeSelect>
            </Field>
            <Field>
              <FieldLabel>Git identity mode</FieldLabel>
              <FieldDescription>Choose between managed, system, or custom commit identity.</FieldDescription>
              <NativeSelect value={form.git_user_mode} onChange={(event) => onGitUserModeChange(event.target.value)}>
                <NativeSelectOption value="kagan_agent">Managed by Kagan</NativeSelectOption>
                <NativeSelectOption value="system_default">Use system git config</NativeSelectOption>
                <NativeSelectOption value="custom">Custom identity</NativeSelectOption>
              </NativeSelect>
            </Field>
            <Field>
              <FieldLabel>Git user name</FieldLabel>
              <FieldDescription>Override author name for task commits in custom mode.</FieldDescription>
              <Input
                value={form.git_user_name}
                onChange={(event) => setField('git_user_name', event.target.value)}
                onBlur={() => saveField('git_user_name', form.git_user_name)}
                placeholder={resolvedGit.name}
                disabled={form.git_user_mode !== 'custom'}
              />
            </Field>
            <Field>
              <FieldLabel>Git user email</FieldLabel>
              <FieldDescription>Override author email for task commits in custom mode.</FieldDescription>
              <Input
                value={form.git_user_email}
                onChange={(event) => setField('git_user_email', event.target.value)}
                onBlur={() => saveField('git_user_email', form.git_user_email)}
                placeholder={resolvedGit.email}
                disabled={form.git_user_mode !== 'custom'}
              />
            </Field>
            <Field>
              <FieldLabel>Default Claude model</FieldLabel>
              <FieldDescription>Default model hint when using Claude-family agents.</FieldDescription>
              <Input
                value={form.default_model_claude}
                onChange={(event) => setField('default_model_claude', event.target.value)}
                onBlur={() => saveField('default_model_claude', form.default_model_claude)}
                placeholder="Uses agent default"
              />
            </Field>
            <Field>
              <FieldLabel>Default OpenAI model</FieldLabel>
              <FieldDescription>Default model hint when using OpenAI-family agents.</FieldDescription>
              <Input
                value={form.default_model_openai}
                onChange={(event) => setField('default_model_openai', event.target.value)}
                onBlur={() => saveField('default_model_openai', form.default_model_openai)}
                placeholder="Uses agent default"
              />
            </Field>
          </FieldSet>

          <FieldSeparator />

          <AdditionalInstructionsSettings
            form={form}
            savedValue={savedRef.current.additional_instructions}
            setField={setField}
            saveField={saveField}
            dotfileOverrides={dotfileOverrides}
          />
        </FieldGroup>
      )}
    </Card>
  );
}
