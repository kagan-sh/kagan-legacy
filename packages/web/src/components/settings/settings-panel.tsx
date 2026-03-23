import { useEffect, useRef, useState } from 'react';
import { useAtom, useSetAtom } from 'jotai';
import { Check, Undo2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { themeModeAtom, setThemeModeAtom } from '@/lib/atoms/theme';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
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
import { asBool } from '@/lib/utils';

type ThemeMode = 'system' | 'dark' | 'light';

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
};

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
  const [resolvedGit, setResolvedGit] = useState<{ name: string; email: string }>({
    name: '',
    email: '',
  });
  const [dotfileOverrides, setDotfileOverrides] = useState<Record<string, string | null>>({});

  const [loading, setLoading] = useState(true);
  const [availableBackends, setAvailableBackends] = useState<string[]>([]);

  const setField = <K extends keyof SettingsFormState>(
    key: K,
    value: SettingsFormState[K],
  ) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const saveField = async <K extends keyof SettingsFormState>(
    key: K,
    value: SettingsFormState[K],
  ) => {
    setField(key, value);
    try {
      const apiValue =
        typeof value === 'boolean' ? String(value) : (value as string);
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

        setAvailableBackends(agents.backends.map((b) => b.name));

        setResolvedGit({
          name: resolved.git_user_name || '',
          email: resolved.git_user_email || '',
        });

        setDotfileOverrides(resolved.dotfile_overrides || {});

        const loaded: SettingsFormState = {
          attached_launcher: settings.attached_launcher || DEFAULT_FORM.attached_launcher,
          default_base_branch: settings.default_base_branch || DEFAULT_FORM.default_base_branch,
          worktree_base_ref_strategy: settings.worktree_base_ref_strategy || DEFAULT_FORM.worktree_base_ref_strategy,
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
          require_review_approval: asBool(settings.require_review_approval, DEFAULT_FORM.require_review_approval),
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

  const detectedDotfileOverrides = Object.entries(dotfileOverrides)
    .filter(([, v]) => v != null)
    .map(([k]) => k);

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

          <FieldSet>
            <FieldLegend variant="label">Essentials</FieldLegend>
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
              <FieldLabel>Theme</FieldLabel>
              <FieldDescription>Choose how Kagan renders across desktop and mobile surfaces.</FieldDescription>
              <NativeSelect
                value={themeMode}
                onChange={(event) => setThemeMode(event.target.value as ThemeMode)}
              >
                <NativeSelectOption value="system">Follow system</NativeSelectOption>
                <NativeSelectOption value="dark">Dark</NativeSelectOption>
                <NativeSelectOption value="light">Light</NativeSelectOption>
              </NativeSelect>
            </Field>
            <Field>
              <FieldLabel>Instructions</FieldLabel>
              <FieldDescription>Appended to every agent prompt — your preferences, conventions, and workflow rules.</FieldDescription>
              <Textarea
                rows={4}
                value={form.additional_instructions}
                onChange={(event) => setField('additional_instructions', event.target.value)}
                placeholder="Use conventional commits · Explain tradeoffs first · Commit messages in Portuguese"
              />
              {form.additional_instructions !== savedRef.current.additional_instructions && (
                <div className="flex items-center justify-end gap-2 pt-1.5">
                  <span className="text-[11px] text-[var(--muted-foreground)]">Unsaved changes</span>
                  <Button variant="ghost" size="xs" onClick={() => setField('additional_instructions', savedRef.current.additional_instructions)}>
                    <Undo2 className="size-3" /> Discard
                  </Button>
                  <Button size="xs" onClick={() => saveField('additional_instructions', form.additional_instructions)}>
                    <Check className="size-3" /> Apply
                  </Button>
                </div>
              )}
              <div className="pt-2 text-[11px] text-[var(--muted-foreground)]">
                {detectedDotfileOverrides.length > 0 ? (
                  <span>Prompt overrides active: <strong>{detectedDotfileOverrides.join(', ')}</strong></span>
                ) : (
                  <span>Full prompt overrides → <code className="text-[10px]">.kagan/prompts/</code></span>
                )}
              </div>
            </Field>
          </FieldSet>

          <FieldSeparator />

          <FieldSet>
            <FieldLegend variant="label">Workflow</FieldLegend>
            <ToggleRow
              title="Auto review"
              description="Run review checks automatically when task execution completes."
              checked={form.auto_review}
              onCheckedChange={(value) => saveField('auto_review', value)}
            />
            <ToggleRow
              title="Require review approval"
              description="Block merge transitions unless reviewer approval is present."
              checked={form.require_review_approval}
              onCheckedChange={(value) => saveField('require_review_approval', value)}
            />
            <ToggleRow
              title="Auto-confirm single tasks"
              description="Skip the confirmation step for single-task plans and proceed directly to execution."
              checked={form.auto_confirm_single_tasks}
              onCheckedChange={(value) => saveField('auto_confirm_single_tasks', value)}
            />
            <Field>
              <FieldLabel>Review strictness</FieldLabel>
              <FieldDescription>Controls how thoroughly task outputs are reviewed before approval.</FieldDescription>
              <NativeSelect
                value={form.review_strictness}
                onChange={(event) => saveField('review_strictness', event.target.value)}
              >
                <NativeSelectOption value="strict">Strict</NativeSelectOption>
                <NativeSelectOption value="balanced">Balanced</NativeSelectOption>
                <NativeSelectOption value="relaxed">Relaxed</NativeSelectOption>
              </NativeSelect>
            </Field>
          </FieldSet>

          <FieldSeparator />

          <FieldSet>
            <FieldLegend variant="label">Git</FieldLegend>
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
              <FieldLabel>Default base branch</FieldLabel>
              <FieldDescription>Base branch used for task worktrees when none is specified.</FieldDescription>
              <Input
                value={form.default_base_branch}
                onChange={(event) => setField('default_base_branch', event.target.value)}
                onBlur={() => saveField('default_base_branch', form.default_base_branch)}
              />
            </Field>
          </FieldSet>

          <FieldSeparator />

          <FieldSet>
            <details className="space-y-6">
              <summary className="cursor-pointer text-sm font-medium text-muted-foreground hover:text-foreground">
                Advanced settings
              </summary>
              <Field>
                <FieldLabel>Worktree base strategy</FieldLabel>
                <FieldDescription>Controls whether worktrees anchor to local or remote references.</FieldDescription>
                <NativeSelect
                  value={form.worktree_base_ref_strategy}
                  onChange={(event) => saveField('worktree_base_ref_strategy', event.target.value)}
                >
                  <NativeSelectOption value="local_if_ahead">local_if_ahead</NativeSelectOption>
                  <NativeSelectOption value="remote">remote</NativeSelectOption>
                  <NativeSelectOption value="local">local</NativeSelectOption>
                </NativeSelect>
              </Field>
              <Field>
                <FieldLabel>Planning depth</FieldLabel>
                <FieldDescription>When the orchestrator creates detailed task plans before execution.</FieldDescription>
                <NativeSelect
                  value={form.planning_depth}
                  onChange={(event) => saveField('planning_depth', event.target.value)}
                >
                  <NativeSelectOption value="always">Always plan</NativeSelectOption>
                  <NativeSelectOption value="multi_task">Multi-task only</NativeSelectOption>
                  <NativeSelectOption value="never">Never plan</NativeSelectOption>
                </NativeSelect>
              </Field>
              <ToggleRow
                title="Serialize merges"
                description="Queue manual merges to avoid branch collision under high throughput."
                checked={form.serialize_merges}
                onCheckedChange={(value) => saveField('serialize_merges', value)}
              />
              <ToggleRow
                title="Auto-initialize git repository"
                description="Initialize git automatically when creating a fresh workspace."
                checked={form.auto_init_git_repo}
                onCheckedChange={(value) => saveField('auto_init_git_repo', value)}
              />
              <ToggleRow
                title="Create initial commit automatically"
                description="Create a bootstrap commit after automatic repository initialization."
                checked={form.auto_init_git_initial_commit}
                onCheckedChange={(value) => saveField('auto_init_git_initial_commit', value)}
              />
              <Field>
                <FieldLabel>Interactive launcher</FieldLabel>
                <FieldDescription>Primary tool used when you attach an interactive run.</FieldDescription>
                <NativeSelect
                  value={form.attached_launcher}
                  onChange={(event) => saveField('attached_launcher', event.target.value)}
                >
                  <NativeSelectOption value="tmux">tmux</NativeSelectOption>
                  <NativeSelectOption value="nvim">nvim</NativeSelectOption>
                  <NativeSelectOption value="vscode">vscode</NativeSelectOption>
                  <NativeSelectOption value="cursor">cursor</NativeSelectOption>
                  <NativeSelectOption value="windsurf">windsurf</NativeSelectOption>
                  <NativeSelectOption value="kiro">kiro</NativeSelectOption>
                  <NativeSelectOption value="antigravity">antigravity</NativeSelectOption>
                </NativeSelect>
              </Field>
              <ToggleRow
                title="Restore last workspace on startup"
                description="Resume directly in your recent project context after app launch."
                checked={form.open_last_project_on_startup}
                onCheckedChange={(value) => saveField('open_last_project_on_startup', value)}
              />
              <ToggleRow
                title="Show attach guidance"
                description="Keep onboarding instructions visible when attaching an interactive run."
                checked={!form.skip_attached_instructions_popup}
                onCheckedChange={(value) => saveField('skip_attached_instructions_popup', !value)}
              />
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
            </details>
          </FieldSet>

        </FieldGroup>
      )}
    </Card>
  );
}
