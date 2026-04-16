import { useAtom, useSetAtom } from 'jotai';
import type { UseSettingsFormResult } from './use-settings-form';
import { ToggleRow } from './toggle-row';
import { themeModeAtom, setThemeModeAtom } from '@/lib/atoms/theme';
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
} from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';

type ThemeMode = 'system' | 'dark' | 'light';

interface Props {
  controller: UseSettingsFormResult;
}

export function SettingsSectionAdvanced({ controller }: Props) {
  const { form, resolvedGit, setField, saveField, onGitUserModeChange } = controller;
  const [themeMode] = useAtom(themeModeAtom);
  const setThemeMode = useSetAtom(setThemeModeAtom);

  return (
    <FieldGroup className="space-y-0">
      <FieldSet>
        <FieldLegend variant="label">Appearance</FieldLegend>
        <Field>
          <FieldLabel>Theme</FieldLabel>
          <FieldDescription>
            Choose how Kagan renders across desktop and mobile surfaces.
          </FieldDescription>
          <NativeSelect
            value={themeMode}
            onChange={(event) => setThemeMode(event.target.value as ThemeMode)}
          >
            <NativeSelectOption value="system">Follow system</NativeSelectOption>
            <NativeSelectOption value="dark">Dark</NativeSelectOption>
            <NativeSelectOption value="light">Light</NativeSelectOption>
          </NativeSelect>
        </Field>
      </FieldSet>

      <FieldSeparator />

      <FieldSet>
        <FieldLegend variant="label">Git identity</FieldLegend>
        <Field>
          <FieldLabel>Git identity mode</FieldLabel>
          <FieldDescription>
            Choose between managed, system, or custom commit identity.
          </FieldDescription>
          <NativeSelect
            value={form.git_user_mode}
            onChange={(event) => onGitUserModeChange(event.target.value)}
          >
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
      </FieldSet>

      <FieldSeparator />

      <FieldSet>
        <FieldLegend variant="label">Workspace bootstrap</FieldLegend>
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
        <ToggleRow
          title="Restore last workspace on startup"
          description="Resume directly in your recent project context after app launch."
          checked={form.open_last_project_on_startup}
          onCheckedChange={(value) => saveField('open_last_project_on_startup', value)}
        />
      </FieldSet>

      <FieldSeparator />

      <FieldSet>
        <FieldLegend variant="label">Attach</FieldLegend>
        <Field>
          <FieldLabel>Interactive launcher</FieldLabel>
          <FieldDescription>
            Primary tool used when you attach an interactive run.
          </FieldDescription>
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
          title="Show attach guidance"
          description="Keep onboarding instructions visible when attaching an interactive run."
          checked={!form.skip_attached_instructions_popup}
          onCheckedChange={(value) => saveField('skip_attached_instructions_popup', !value)}
        />
      </FieldSet>
    </FieldGroup>
  );
}
