import { Check, Undo2 } from 'lucide-react';
import type { SettingsFormState } from '../settings-panel';
import { Field, FieldDescription, FieldLabel, FieldSet, FieldLegend } from '@/components/ui/field';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';

interface SectionProps {
  form: SettingsFormState;
  savedValue: string;
  setField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
  saveField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
  dotfileOverrides: Record<string, string | null>;
}

export function AdditionalInstructionsSettings({ form, savedValue, setField, saveField, dotfileOverrides }: SectionProps) {
  const detected = Object.entries(dotfileOverrides)
    .filter(([, v]) => v != null)
    .map(([k]) => k);

  return (
    <FieldSet>
      <FieldLegend variant="label">Additional Instructions</FieldLegend>
      <Field>
        <FieldLabel>Instructions</FieldLabel>
        <FieldDescription>Appended to every agent prompt — your preferences, conventions, and workflow rules.</FieldDescription>
        <Textarea
          rows={4}
          value={form.additional_instructions}
          onChange={(event) => setField('additional_instructions', event.target.value)}
          placeholder="Use conventional commits · Explain tradeoffs first · Commit messages in Portuguese"
        />
        {form.additional_instructions !== savedValue && (
          <div className="flex items-center justify-end gap-2 pt-1.5">
            <span className="text-[11px] text-[var(--muted-foreground)]">Unsaved changes</span>
            <Button variant="ghost" size="xs" onClick={() => setField('additional_instructions', savedValue)}>
              <Undo2 className="size-3" /> Discard
            </Button>
            <Button size="xs" onClick={() => saveField('additional_instructions', form.additional_instructions)}>
              <Check className="size-3" /> Apply
            </Button>
          </div>
        )}
      </Field>
      <div className="pt-2 text-[11px] text-[var(--muted-foreground)]">
        {detected.length > 0 ? (
          <span>Prompt overrides active: <strong>{detected.join(', ')}</strong></span>
        ) : (
          <span>Full prompt overrides → <code className="text-[10px]">.kagan/prompts/</code></span>
        )}
      </div>
    </FieldSet>
  );
}
