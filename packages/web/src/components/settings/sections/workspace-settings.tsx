import type { SettingsFormState } from '../settings-panel';
import { ToggleRow } from '../settings-panel';
import { Field, FieldDescription, FieldLabel, FieldSet, FieldLegend } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';

interface SectionProps {
  form: SettingsFormState;
  setField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
  saveField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
}

export function WorkspaceSettings({ form, setField, saveField }: SectionProps) {
  return (
      <FieldSet>
        <FieldLegend variant="label">Workspace Defaults</FieldLegend>
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
      <Field>
        <FieldLabel>Default base branch</FieldLabel>
        <FieldDescription>Base branch used for task worktrees when none is specified.</FieldDescription>
        <Input
          value={form.default_base_branch}
          onChange={(event) => setField('default_base_branch', event.target.value)}
          onBlur={() => saveField('default_base_branch', form.default_base_branch)}
        />
      </Field>
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
    </FieldSet>
  );
}
