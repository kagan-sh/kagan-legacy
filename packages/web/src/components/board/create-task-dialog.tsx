import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Plus, X } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import { useSetAtom } from 'jotai';
import { fetchTasksAtom } from '@/lib/atoms/board';
import { toast } from 'sonner';
import { LAUNCHER_OPTIONS } from '@/lib/utils/constants';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Button } from '@/components/ui/button';

const createTaskSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  description: z.string().optional(),
  priority: z.enum(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']),
  agent_backend: z.string().optional(),
  launcher: z.string().optional(),
  base_branch: z.string().optional(),
});

type CreateTaskForm = z.infer<typeof createTaskSchema>;

interface CreateTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateTaskDialog({
  open,
  onOpenChange,
}: CreateTaskDialogProps) {
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const [submitting, setSubmitting] = useState(false);
  const [backends, setBackends] = useState<string[]>([]);
  const [criteria, setCriteria] = useState<string[]>([]);
  const [criterionInput, setCriterionInput] = useState('');

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateTaskForm>({
    resolver: zodResolver(createTaskSchema),
    defaultValues: { priority: 'MEDIUM' },
  });

  useEffect(() => {
    if (!open) return;
    apiClient.getChatAgents().then((data) => setBackends(data.backends)).catch(() => {});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    reset({
      title: '',
      description: '',
      priority: 'MEDIUM',
      agent_backend: '',
      launcher: '',
      base_branch: '',
    });
    setCriteria([]);
    setCriterionInput('');
  }, [open, reset]);

  const addCriterion = () => {
    const trimmed = criterionInput.trim();
    if (!trimmed) return;
    setCriteria((prev) => [...prev, trimmed]);
    setCriterionInput('');
  };

  const removeCriterion = (index: number) => {
    setCriteria((prev) => prev.filter((_, i) => i !== index));
  };

  const onSubmit = async (data: CreateTaskForm) => {
    setSubmitting(true);
    try {
      await apiClient.createTask({
        ...data,
        agent_backend: data.agent_backend || undefined,
        launcher: data.launcher || undefined,
        base_branch: data.base_branch?.trim() || undefined,
        acceptance_criteria: criteria.length > 0 ? criteria : undefined,
      });
      toast.success('Task created');
      fetchTasks();
      reset();
      setCriteria([]);
      setCriterionInput('');
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create task');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Create Task</DialogTitle>
          <DialogDescription>
            Define task details, priority, and acceptance criteria.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="title" className="mb-1">Title</Label>
            <Input
              id="title"
              {...register('title')}
              placeholder="What needs to be done?"
              autoFocus
              aria-describedby={errors.title ? 'title-error' : undefined}
              aria-invalid={errors.title ? 'true' : 'false'}
            />
            {errors.title && (
              <p id="title-error" className="mt-1 text-xs text-[var(--destructive)]">{errors.title.message}</p>
            )}
          </div>

          <div>
            <Label htmlFor="description" className="mb-1">Description</Label>
            <Textarea
              id="description"
              {...register('description')}
              rows={3}
              placeholder="Optional details..."
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <Label htmlFor="priority" className="mb-1">Priority</Label>
              <NativeSelect id="priority" {...register('priority')} className="w-full">
                <NativeSelectOption value="LOW">Low</NativeSelectOption>
                <NativeSelectOption value="MEDIUM">Medium</NativeSelectOption>
                <NativeSelectOption value="HIGH">High</NativeSelectOption>
                <NativeSelectOption value="CRITICAL">Critical</NativeSelectOption>
              </NativeSelect>
            </div>
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <Label htmlFor="agent_backend" className="mb-1">Agent Backend</Label>
              <NativeSelect id="agent_backend" {...register('agent_backend')} className="w-full">
                <NativeSelectOption value="">Default</NativeSelectOption>
                {backends.map((b) => (
                  <NativeSelectOption key={b} value={b}>{b}</NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
            <div className="flex-1">
              <Label htmlFor="launcher" className="mb-1">Launcher</Label>
              <NativeSelect id="launcher" {...register('launcher')} className="w-full">
                <NativeSelectOption value="">Default</NativeSelectOption>
                {LAUNCHER_OPTIONS.map((l) => (
                  <NativeSelectOption key={l} value={l}>{l}</NativeSelectOption>
                ))}
              </NativeSelect>
            </div>
          </div>

          <div>
            <Label htmlFor="base_branch" className="mb-1">Base Branch</Label>
            <Input
              id="base_branch"
              {...register('base_branch')}
              placeholder="e.g. main (uses project default if empty)"
            />
          </div>

          <div>
            <Label className="mb-1">Acceptance Criteria</Label>
            <div className="flex gap-2">
              <Input
                value={criterionInput}
                onChange={(e) => setCriterionInput(e.target.value)}
                placeholder="Add a success criterion..."
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    addCriterion();
                  }
                }}
              />
              <Button type="button" variant="outline" size="icon" onClick={addCriterion} aria-label="Add criterion">
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
                      onClick={() => removeCriterion(i)}
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

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" type="button" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              <Plus className="size-4" />
              {submitting ? 'Creating...' : 'Create'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
