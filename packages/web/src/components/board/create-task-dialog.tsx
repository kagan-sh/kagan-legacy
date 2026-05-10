import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Plus } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import { useAtomValue, useSetAtom } from 'jotai';
import { boardRepoFilterAtom, fetchTasksAtom } from '@/lib/atoms/board';
import { toast } from 'sonner';
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

interface CreateTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateTaskDialog({ open, onOpenChange }: CreateTaskDialogProps) {
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const activeRepoId = useAtomValue(boardRepoFilterAtom);
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
    defaultValues: { priority: 'MEDIUM', github_issue_mode: 'none' },
  });

  useEffect(() => {
    if (!open) return;
    reset({ title: '', description: '', priority: 'MEDIUM', agent_backend: '', launcher: '', base_branch: '', github_issue_mode: 'none', github_issue_number: '' });
    criteriaList.reset();
  }, [open, reset]); // eslint-disable-line react-hooks/exhaustive-deps

  const onSubmit = async (data: TaskFormValues) => {
    setSubmitting(true);
    try {
      await apiClient.createTask({
        ...data,
        agent_backend: data.agent_backend || undefined,
        launcher: data.launcher || undefined,
        base_branch: data.base_branch?.trim() || undefined,
        acceptance_criteria: criteriaList.criteria.length > 0 ? criteriaList.criteria : undefined,
        repo_id: activeRepoId ?? undefined,
        github_issue: resolveGithubIssue(data),
      });
      toast.success('Task created');
      fetchTasks();
      reset();
      criteriaList.reset();
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
          <DialogTitle>Create task</DialogTitle>
          <DialogDescription>Define task details, priority, and acceptance criteria.</DialogDescription>
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
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" type="button" onClick={() => onOpenChange(false)}>Cancel</Button>
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
