import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Pencil } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import { useSetAtom } from 'jotai';
import { fetchTasksAtom } from '@/lib/atoms/board';
import { toast } from 'sonner';
import type { WireTask } from '@kagan/shared-api-client';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  taskSchema,
  type TaskFormValues,
  useBackendOptions,
  useCriteriaList,
  useGithubRepoSlug,
  resolveGithubIssue,
  TaskFormFields,
} from '@/components/board/task-form';

interface EditTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: WireTask | null;
  onUpdated?: (task: WireTask) => void;
}

export function EditTaskDialog({ open, onOpenChange, task, onUpdated }: EditTaskDialogProps) {
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const [submitting, setSubmitting] = useState(false);
  const backends = useBackendOptions(open);
  const criteriaList = useCriteriaList();
  const githubRepoSlug = useGithubRepoSlug(open);

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<TaskFormValues>({
    resolver: zodResolver(taskSchema),
    defaultValues: { title: '', description: '', priority: 'MEDIUM', agent_backend: '', launcher: '', base_branch: '', github_issue_mode: 'none' },
  });

  useEffect(() => {
    if (!task) {
      reset({ title: '', description: '', priority: 'MEDIUM', agent_backend: '', launcher: '', base_branch: '' });
      criteriaList.reset();
      return;
    }

    reset({
      title: task.title,
      description: task.description ?? '',
      priority: task.priority as TaskFormValues['priority'],
      agent_backend: task.agent_backend ?? '',
      launcher: task.launcher ?? '',
      base_branch: task.base_branch ?? '',
    });
    criteriaList.reset((task.acceptance_criteria ?? []).map((c) => c.text));
  }, [task, reset]); // eslint-disable-line react-hooks/exhaustive-deps

  const onSubmit = async (data: TaskFormValues) => {
    if (!task) return;

    setSubmitting(true);
    try {
      const updatedTask = await apiClient.updateTask(task.id, {
        title: data.title.trim(),
        description: data.description?.trim() || undefined,
        priority: data.priority,
        agent_backend: data.agent_backend?.trim() || undefined,
        launcher: data.launcher || undefined,
        base_branch: data.base_branch?.trim() || undefined,
        acceptance_criteria: criteriaList.criteria,
        github_issue: resolveGithubIssue(data),
      });

      toast.success('Task updated');
      onUpdated?.(updatedTask);
      fetchTasks();
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update task');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Task</DialogTitle>
          <DialogDescription>Update task details, agent config, and acceptance criteria.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <TaskFormFields
            register={register}
            control={control}
            errors={errors}
            backends={backends}
            criteria={criteriaList.criteria}
            criterionInput={criteriaList.input}
            onCriterionInputChange={criteriaList.setInput}
            onAddCriterion={criteriaList.add}
            onRemoveCriterion={criteriaList.remove}
            githubRepoSlug={githubRepoSlug}
            idPrefix="edit-"
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" type="button" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={submitting || !task}>
              <Pencil className="size-4" />
              {submitting ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
