import type { SettingsFormState } from '../settings-panel';
import { ToggleRow } from '../settings-panel';
import { FieldSet, FieldLegend } from '@/components/ui/field';

interface SectionProps {
  form: SettingsFormState;
  saveField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
}

export function WorkflowSettings({ form, saveField }: SectionProps) {
  return (
    <FieldSet>
      <FieldLegend variant="label">Delivery Automation</FieldLegend>
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
        title="Serialize merges"
        description="Queue manual merges to avoid branch collision under high throughput."
        checked={form.serialize_merges}
        onCheckedChange={(value) => saveField('serialize_merges', value)}
      />
    </FieldSet>
  );
}
