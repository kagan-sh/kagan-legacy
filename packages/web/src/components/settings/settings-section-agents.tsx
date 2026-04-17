import { Check, Undo2 } from 'lucide-react';
import type { UseSettingsFormResult } from './use-settings-form';
import { ToggleRow } from './toggle-row';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import { Textarea } from '@/components/ui/textarea';

interface Props {
  controller: UseSettingsFormResult;
}

export function SettingsSectionAgents({ controller }: Props) {
  const { form, savedRef, availableBackends, dotfileOverrides, setField, saveField } = controller;

  const sortedBackends = [...availableBackends].sort((a, b) => {
    if (a.reference !== b.reference) return a.reference ? -1 : 1;
    if (a.available !== b.available) return a.available ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  const selectedBackend = availableBackends.find(
    (backend) => backend.name === form.default_agent_backend,
  );

  const detectedDotfileOverrides = Object.entries(dotfileOverrides)
    .filter(([, v]) => v != null)
    .map(([k]) => k);

  return (
    <FieldGroup className="space-y-0">
      <FieldSet>
        <FieldLegend variant="label">Default backend</FieldLegend>
        <Field>
          <FieldLabel>Default agent backend</FieldLabel>
          <FieldDescription>
            Agent used for new tasks when none is specified. Reference backends are highlighted first.
          </FieldDescription>
          <NativeSelect
            value={form.default_agent_backend}
            onChange={(event) => saveField('default_agent_backend', event.target.value)}
          >
            {sortedBackends.length > 0 ? (
              sortedBackends.map((backend) => (
                <NativeSelectOption key={backend.name} value={backend.name}>
                  {backend.name}
                  {backend.reference ? ' (reference)' : ''}
                  {!backend.available ? ' (unavailable)' : ''}
                </NativeSelectOption>
              ))
            ) : (
              <NativeSelectOption value={form.default_agent_backend}>
                {form.default_agent_backend}
              </NativeSelectOption>
            )}
          </NativeSelect>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-[var(--muted-foreground)]">
            {selectedBackend?.reference && <Badge variant="outline">Reference</Badge>}
            {selectedBackend && !selectedBackend.available && (
              <Badge variant="secondary">Unavailable</Badge>
            )}
            {selectedBackend && !selectedBackend.available ? (
              <span>Choose an available reference backend if the default cannot start.</span>
            ) : (
              <span>Prefer a reference backend when you want the most supported path.</span>
            )}
          </div>
        </Field>
        <ToggleRow
          title="Use recommended backend"
          description="Automatically pick the highest-success backend based on analytics. Overrides manual selection."
          checked={form.use_recommended_backend}
          onCheckedChange={(value) => saveField('use_recommended_backend', value)}
        />
      </FieldSet>

      <FieldSeparator />

      <FieldSet>
        <FieldLegend variant="label">Model hints</FieldLegend>
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

      <FieldSet>
        <FieldLegend variant="label">Instructions</FieldLegend>
        <Field>
          <FieldLabel>Additional instructions</FieldLabel>
          <FieldDescription>
            Appended to every agent prompt — your preferences, conventions, and workflow rules.
          </FieldDescription>
          <Textarea
            rows={4}
            value={form.additional_instructions}
            onChange={(event) => setField('additional_instructions', event.target.value)}
            placeholder="Use conventional commits · Explain tradeoffs first · Commit messages in Portuguese"
          />
          {form.additional_instructions !== savedRef.current.additional_instructions && (
            <div className="flex items-center justify-end gap-2 pt-1.5">
              <span className="text-[11px] text-[var(--muted-foreground)]">Unsaved changes</span>
              <Button
                variant="ghost"
                size="xs"
                onClick={() =>
                  setField('additional_instructions', savedRef.current.additional_instructions)
                }
              >
                <Undo2 className="size-3" /> Discard
              </Button>
              <Button
                size="xs"
                onClick={() => saveField('additional_instructions', form.additional_instructions)}
              >
                <Check className="size-3" /> Apply
              </Button>
            </div>
          )}
          <div className="pt-2 text-[11px] text-[var(--muted-foreground)]">
            {detectedDotfileOverrides.length > 0 ? (
              <span>
                Prompt overrides active: <strong>{detectedDotfileOverrides.join(', ')}</strong>
              </span>
            ) : (
              <span>
                Full prompt overrides → <code className="text-[10px]">.kagan/prompts/</code>
              </span>
            )}
          </div>
        </Field>
      </FieldSet>
    </FieldGroup>
  );
}
