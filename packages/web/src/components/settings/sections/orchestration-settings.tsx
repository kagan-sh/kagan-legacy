import type { SettingsFormState } from '../settings-panel';
import { ToggleRow } from '../settings-panel';
import { Field, FieldDescription, FieldLabel, FieldSet, FieldLegend } from '@/components/ui/field';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';

interface SectionProps {
  form: SettingsFormState;
  saveField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
}

export function OrchestrationSettings({ form, saveField }: SectionProps) {
  return (
    <FieldSet>
      <FieldLegend variant="label">Orchestration</FieldLegend>
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
    </FieldSet>
  );
}
