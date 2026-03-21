import type { SettingsFormState } from '../settings-panel';
import { ToggleRow } from '../settings-panel';
import { Field, FieldDescription, FieldLabel, FieldSet, FieldLegend } from '@/components/ui/field';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';

type ThemeMode = 'system' | 'dark' | 'light';

interface SectionProps {
  form: SettingsFormState;
  setField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
  saveField: <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => void;
  themeMode: ThemeMode;
  setThemeMode: (mode: ThemeMode) => void;
}

export function AppearanceSettings({ form, saveField, themeMode, setThemeMode }: SectionProps) {
  return (
    <FieldSet>
      <FieldLegend variant="label">Interface</FieldLegend>
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
      <ToggleRow
        title="Show attach guidance"
        description="Keep onboarding instructions visible when attaching an interactive run."
        checked={!form.skip_attached_instructions_popup}
        onCheckedChange={(value) => saveField('skip_attached_instructions_popup', !value)}
      />
      <ToggleRow
        title="Restore last workspace on startup"
        description="Resume directly in your recent project context after app launch."
        checked={form.open_last_project_on_startup}
        onCheckedChange={(value) => saveField('open_last_project_on_startup', value)}
      />
    </FieldSet>
  );
}
