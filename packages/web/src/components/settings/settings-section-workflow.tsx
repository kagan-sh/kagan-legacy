import type { UseSettingsFormResult } from './use-settings-form';
import { ToggleRow } from './toggle-row';
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

interface Props {
  controller: UseSettingsFormResult;
}

export function SettingsSectionWorkflow({ controller }: Props) {
  const { form, setField, saveField } = controller;

  return (
    <FieldGroup className="space-y-0">
      <FieldSet>
        <FieldLegend variant="label">Review</FieldLegend>
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
          <FieldDescription>
            Controls how thoroughly task outputs are reviewed before approval.
          </FieldDescription>
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
        <FieldLegend variant="label">Planning</FieldLegend>
        <Field>
          <FieldLabel>Planning depth</FieldLabel>
          <FieldDescription>
            When the orchestrator creates detailed task plans before execution.
          </FieldDescription>
          <NativeSelect
            value={form.planning_depth}
            onChange={(event) => saveField('planning_depth', event.target.value)}
          >
            <NativeSelectOption value="always">Always plan</NativeSelectOption>
            <NativeSelectOption value="multi_task">Multi-task only</NativeSelectOption>
            <NativeSelectOption value="never">Never plan</NativeSelectOption>
          </NativeSelect>
        </Field>
      </FieldSet>

      <FieldSeparator />

      <FieldSet>
        <FieldLegend variant="label">Merging</FieldLegend>
        <ToggleRow
          title="Serialize merges"
          description="Queue manual merges to avoid branch collision under high throughput."
          checked={form.serialize_merges}
          onCheckedChange={(value) => saveField('serialize_merges', value)}
        />
        <Field>
          <FieldLabel>Default base branch</FieldLabel>
          <FieldDescription>
            Base branch used for task worktrees when none is specified.
          </FieldDescription>
          <Input
            value={form.default_base_branch}
            onChange={(event) => setField('default_base_branch', event.target.value)}
            onBlur={() => saveField('default_base_branch', form.default_base_branch)}
          />
        </Field>
        <Field>
          <FieldLabel>Worktree base strategy</FieldLabel>
          <FieldDescription>
            Controls whether worktrees anchor to local or remote references.
          </FieldDescription>
          <NativeSelect
            value={form.worktree_base_ref_strategy}
            onChange={(event) => saveField('worktree_base_ref_strategy', event.target.value)}
          >
            <NativeSelectOption value="local_if_ahead">local_if_ahead</NativeSelectOption>
            <NativeSelectOption value="remote">remote</NativeSelectOption>
            <NativeSelectOption value="local">local</NativeSelectOption>
          </NativeSelect>
        </Field>
      </FieldSet>
    </FieldGroup>
  );
}
