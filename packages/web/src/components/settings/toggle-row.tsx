import { Switch } from '@/components/ui/switch';
import { Field, FieldContent, FieldDescription, FieldLabel } from '@/components/ui/field';

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
