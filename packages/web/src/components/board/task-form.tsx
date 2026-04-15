import { useEffect, useState } from 'react';
import type { UseFormRegister, FieldErrors } from 'react-hook-form';
import { Plus, X } from 'lucide-react';
import { z } from 'zod';
import { apiClient } from '@/lib/api/client';
import { LAUNCHER_OPTIONS } from '@/lib/utils/constants';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Button } from '@/components/ui/button';

export const taskSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  description: z.string().optional(),
  priority: z.enum(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']),
  agent_backend: z.string().optional(),
  launcher: z.string().optional(),
  base_branch: z.string().optional(),
});

export type TaskFormValues = z.infer<typeof taskSchema>;

export function useBackendOptions(open: boolean) {
  const [backends, setBackends] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    apiClient.getChatAgents().then((data) => setBackends(data.backends.map((b) => b.name))).catch(() => {});
  }, [open]);

  return backends;
}

export function useCriteriaList(initial: string[] = []) {
  const [criteria, setCriteria] = useState<string[]>(initial);
  const [input, setInput] = useState('');

  const add = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    setCriteria((prev) => [...prev, trimmed]);
    setInput('');
  };

  const remove = (index: number) => {
    setCriteria((prev) => prev.filter((_, i) => i !== index));
  };

  const reset = (values: string[] = []) => {
    setCriteria(values);
    setInput('');
  };

  return { criteria, input, setInput, add, remove, reset };
}

interface TaskFormFieldsProps {
  register: UseFormRegister<TaskFormValues>;
  errors: FieldErrors<TaskFormValues>;
  backends: string[];
  criteria: string[];
  criterionInput: string;
  onCriterionInputChange: (value: string) => void;
  onAddCriterion: () => void;
  onRemoveCriterion: (index: number) => void;
  idPrefix?: string;
}

export function TaskFormFields({
  register,
  errors,
  backends,
  criteria,
  criterionInput,
  onCriterionInputChange,
  onAddCriterion,
  onRemoveCriterion,
  idPrefix = '',
}: TaskFormFieldsProps) {
  const id = (name: string) => `${idPrefix}${name}`;

  return (
    <>
      <div>
        <Label htmlFor={id('title')} className="mb-1">Title</Label>
        <Input
          id={id('title')}
          {...register('title')}
          placeholder="What needs to be done?"
          autoFocus
          aria-describedby={errors.title ? `${id('title')}-error` : undefined}
          aria-invalid={errors.title ? 'true' : 'false'}
        />
        {errors.title && (
          <p id={`${id('title')}-error`} className="mt-1 text-xs text-[var(--destructive)]">{errors.title.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor={id('description')} className="mb-1">Description</Label>
        <Textarea
          id={id('description')}
          {...register('description')}
          rows={3}
          placeholder="Optional details..."
        />
      </div>

      <div className="flex gap-4">
        <div className="flex-1">
          <Label htmlFor={id('priority')} className="mb-1">Priority</Label>
          <NativeSelect id={id('priority')} {...register('priority')} className="w-full">
            <NativeSelectOption value="LOW">Low</NativeSelectOption>
            <NativeSelectOption value="MEDIUM">Medium</NativeSelectOption>
            <NativeSelectOption value="HIGH">High</NativeSelectOption>
            <NativeSelectOption value="CRITICAL">Critical</NativeSelectOption>
          </NativeSelect>
        </div>
      </div>

      <div className="flex gap-4">
        <div className="flex-1">
          <Label htmlFor={id('agent_backend')} className="mb-1">Agent Backend</Label>
          <NativeSelect id={id('agent_backend')} {...register('agent_backend')} className="w-full">
            <NativeSelectOption value="">Default</NativeSelectOption>
            {backends.map((b) => (
              <NativeSelectOption key={b} value={b}>{b}</NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <div className="flex-1">
          <Label htmlFor={id('launcher')} className="mb-1">Launcher</Label>
          <NativeSelect id={id('launcher')} {...register('launcher')} className="w-full">
            <NativeSelectOption value="">Default</NativeSelectOption>
            {LAUNCHER_OPTIONS.map((l) => (
              <NativeSelectOption key={l} value={l}>{l}</NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
      </div>

      <div>
        <Label htmlFor={id('base_branch')} className="mb-1">Base Branch</Label>
        <Input
          id={id('base_branch')}
          {...register('base_branch')}
          placeholder="e.g. main (uses project default if empty)"
        />
      </div>

      <div>
        <Label className="mb-1">Acceptance Criteria</Label>
        <div className="flex gap-2">
          <Input
            value={criterionInput}
            onChange={(e) => onCriterionInputChange(e.target.value)}
            placeholder="Add a success criterion..."
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                onAddCriterion();
              }
            }}
          />
          <Button type="button" variant="outline" size="icon" onClick={onAddCriterion} aria-label="Add criterion">
            <Plus className="size-4" />
          </Button>
        </div>
        {criteria.length > 0 && (
          <ul className="mt-2 space-y-1.5">
            {criteria.map((c, i) => (
              <li key={`${c}-${i}`} className="flex items-start gap-2 bg-[color:var(--surface-1)] px-3 py-2 text-sm">
                <span className="flex-1">{c}</span>
                <button
                  type="button"
                  onClick={() => onRemoveCriterion(i)}
                  className="mt-0.5 shrink-0 text-[var(--muted-foreground)] hover:text-[var(--destructive)]"
                  aria-label={`Remove criterion: ${c}`}
                >
                  <X className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
