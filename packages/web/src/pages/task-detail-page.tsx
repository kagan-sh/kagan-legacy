import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router";
import {
    ArrowLeft,
    CheckCircle,
    ChevronRight,
    ListChecks,
    MessageSquare,
    MoveRight,
    XCircle,
} from "lucide-react";
import { useSetAtom } from "jotai";
import { toast } from "sonner";
import { apiClient } from "@/lib/api/client";
import type { AcceptanceCriterionResponse, ReviewVerdictResponse, TaskStatus, WireTask } from "@kagan/shared-api-client";
import { fetchTasksAtom } from "@/lib/atoms/board";
import {
    STATUS_LABELS,
    getAllowedTaskTransitions,
} from "@/lib/utils/constants";
import { useTaskEvents } from "@/lib/hooks/use-task-events";
import { useSessionOverlay } from "@/lib/hooks/use-session-overlay";
import {
    InspectorSection,
    Panel,
    StickyActionBar,
} from "@/components/shared/workspace";
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription } from "@/components/ui/empty";
import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { AgentControl } from "@/components/board/agent-control";
import { ReviewPanel } from "@/components/board/review-panel";
import { DiffViewer } from "@/components/board/diff-viewer";
import { EditTaskDialog } from "@/components/board/edit-task-dialog";
import { TaskDeleteDialog } from "@/components/board/task-delete-dialog";
import { TaskSidebar } from "@/components/board/task-sidebar";
import { isEditableTarget, hasOpenOverlay } from "@/lib/utils/dom";
export type WorkspaceTab = "overview" | "changes" | "review";

export function defaultTabForTask(task: WireTask): WorkspaceTab {
    if (task.status === "BACKLOG") return "overview";
    if (task.status === "REVIEW" && task.has_workspace) return "review";
    if (task.status === "DONE" && task.review_approved) return "review";
    if (task.has_workspace) return "changes";
    return "overview";
}

export function Component() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const fetchTasks = useSetAtom(fetchTasksAtom);
    const overlay = useSessionOverlay();
    const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
    const [editOpen, setEditOpen] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);

    const [worktreePath, setWorktreePath] = useState<string | null>(null);
    const [attachedLauncher, setAttachedLauncher] = useState<string | null>(null);

    const { task, loading, runningSince } = useTaskEvents(id, {
        initialLimit: 80,
    });

    // 2.4: Set initial tab from URL or task status — only on first load / task change
    const prevTaskIdRef = useRef<string | null>(null);
    useEffect(() => {
        if (!task) return;
        const urlTab = searchParams.get("tab");
        if (
            urlTab === "overview" ||
            urlTab === "changes" ||
            urlTab === "review"
        ) {
            setActiveTab(urlTab);
        } else if (prevTaskIdRef.current !== task.id) {
            setActiveTab(defaultTabForTask(task));
        }
        prevTaskIdRef.current = task.id;
    }, [task, searchParams]);

    useEffect(() => {
        if (!id || !task?.active_session?.launcher) {
            setWorktreePath(null);
            setAttachedLauncher(null);
            return;
        }

        let cancelled = false;

        void apiClient.getTaskWorktree(id).then(
            (res) => {
                if (!cancelled) {
                    setWorktreePath(res.worktree?.path ?? null);
                }
            },
            () => {
                if (!cancelled) {
                    setWorktreePath(null);
                }
            },
        );

        void apiClient.getSettings().then(
            (settings) => {
                if (!cancelled) {
                    setAttachedLauncher(settings.attached_launcher ?? null);
                }
            },
            () => {
                if (!cancelled) {
                    setAttachedLauncher(null);
                }
            },
        );

        return () => {
            cancelled = true;
        };
    }, [id, task?.active_session?.launcher]);

    const handleTransition = async (status: TaskStatus) => {
        if (!id) return;
        try {
            await apiClient.transitionTaskStatus(id, status);
            fetchTasks();
            toast.success(`Moved to ${STATUS_LABELS[status]}`);
        } catch (error) {
            toast.error(
                error instanceof Error ? error.message : "Failed to transition",
            );
        }
    };

    const handleOpenSession = useCallback(async () => {
        if (!task || !id) return;
        try {
            const response = await apiClient.getSessions();
            const taskSession = response.sessions.find((s) => s.task_id === id);
            if (taskSession) {
                overlay.open(taskSession);
            } else {
                toast.error('No session found for this task');
            }
        } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Failed to load sessions');
        }
    }, [id, task, overlay]);

    // Auto-open session overlay when ?lane=worker or ?lane=review is present
    const laneAutoOpenedRef = useRef(false);
    useEffect(() => {
        if (!task || !id) return;
        if (laneAutoOpenedRef.current) return;
        const lane = searchParams.get('lane');
        if (!lane || (lane !== 'worker' && lane !== 'review')) return;
        if (task.active_session?.id) {
            laneAutoOpenedRef.current = true;
            void handleOpenSession();
        }
    }, [id, task, searchParams, handleOpenSession]);

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            if (editOpen || deleteOpen || hasOpenOverlay()) {
                return;
            }

            const editable = isEditableTarget(event.target);
            const lowerKey = event.key.toLowerCase();
            if (!editable && event.key === "Escape") {
                event.preventDefault();
                navigate("/board");
                return;
            }

            if (!editable && lowerKey === "e") {
                event.preventDefault();
                setEditOpen(true);
            }
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [deleteOpen, editOpen, navigate]);

    if (loading) {
        return (
            <div className="mx-auto flex h-full w-full max-w-[1680px] items-center justify-center px-6 py-10">
                <div className="h-14 w-56 animate-pulse bg-[var(--muted)]" />
            </div>
        );
    }

    if (!task) {
        return (
            <div className="mx-auto flex h-full w-full max-w-[1680px] items-center justify-center px-6 py-10">
                <Empty className="border-0">
                    <EmptyHeader>
                        <EmptyTitle>Task not found</EmptyTitle>
                        <EmptyDescription>The task may have been deleted or the workspace is no longer synced with the server.</EmptyDescription>
                    </EmptyHeader>
                </Empty>
            </div>
        );
    }

    const criteria = task.acceptance_criteria ?? [];
    const showReviewTab =
        task.status === "REVIEW" ||
        (task.status === "DONE" && task.review_approved);

    return (
        <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-5 px-4 py-4 sm:px-6">
            <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] pb-3">
                <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => navigate("/board")}
                    aria-label="Go back"
                >
                    <ArrowLeft className="size-4" />
                </Button>
                <h1 className="min-w-0 truncate text-sm font-semibold">
                    {task.title}
                </h1>
            </div>

            <Panel className="mt-3">
                <StickyActionBar>
                    <AgentControl
                        taskId={task.id}
                        status={task.status}
                        startedAt={runningSince}
                        buttonSize="sm"
                        worktreePath={worktreePath}
                        attachedLauncher={attachedLauncher}
                        taskLauncher={task.launcher}
                        activeSessionId={task.active_session?.id ?? null}
                        activeSessionLauncher={
                            task.active_session?.launcher ?? null
                        }
                    />
                    <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleOpenSession}
                    >
                        <MessageSquare className="size-4" />
                        Open session
                    </Button>
                    <Select
                        value=""
                        onValueChange={(value) =>
                            handleTransition(value as TaskStatus)
                        }
                    >
                        <SelectTrigger
                            aria-label="Move task status"
                            size="sm"
                            className="w-auto text-xs"
                        >
                            <MoveRight className="mr-1 size-3.5" />
                            <SelectValue placeholder="Move to..." />
                        </SelectTrigger>
                        <SelectContent>
                            {getAllowedTaskTransitions(
                                task.status as TaskStatus,
                            ).map((status) => (
                                <SelectItem key={status} value={status}>
                                    {STATUS_LABELS[status]}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </StickyActionBar>

                <div className="grid gap-5 p-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
                    <Panel className="overflow-hidden border-none shadow-none">
                        <Tabs
                            value={activeTab}
                            onValueChange={(value) => {
                                if (value === "review" && !showReviewTab)
                                    return;
                                setActiveTab(value as WorkspaceTab);
                            }}
                        >
                            <div className="border-b border-[color:var(--border-subtle)] px-5 py-4">
                                <TabsList
                                    variant="line"
                                    className="w-full justify-start gap-2 bg-transparent p-0"
                                >
                                    <TabsTrigger value="overview">
                                        Overview
                                    </TabsTrigger>
                                    <TabsTrigger value="changes">
                                        Changes
                                    </TabsTrigger>
                                    {showReviewTab ? (
                                        <TabsTrigger value="review">
                                            Review
                                        </TabsTrigger>
                                    ) : null}
                                </TabsList>
                            </div>

                            <TabsContent value="overview" className="p-5">
                                <div className="grid gap-4">
                                    <InspectorSection title="Description">
                                        <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                                            {task.description ||
                                                "No written description yet."}
                                        </p>
                                    </InspectorSection>

                                    <InspectorSection title="Acceptance Criteria">
                                        <CriteriaList
                                            criteria={criteria}
                                            verdicts={task.review_verdicts}
                                        />
                                    </InspectorSection>
                                </div>
                            </TabsContent>

                            <TabsContent value="changes" className="p-5">
                                <div className="grid gap-4">
                                    {task.has_workspace ? (
                                        <DiffViewer
                                            taskId={task.id}
                                            taskStatus={task.status}
                                        />
                                    ) : task.status === "DONE" ? (
                                        <Empty className="border-0">
                                            <EmptyHeader>
                                                <EmptyTitle>Changes merged</EmptyTitle>
                                                <EmptyDescription>This task's branch has been merged and the workspace cleaned up. The diff is no longer available.</EmptyDescription>
                                            </EmptyHeader>
                                        </Empty>
                                    ) : (
                                        <Empty className="border-0">
                                            <EmptyHeader>
                                                <EmptyTitle>Workspace not ready</EmptyTitle>
                                                <EmptyDescription>Provision or start the task to let Kagan create a working tree. Once code starts moving, diffs will appear here.</EmptyDescription>
                                            </EmptyHeader>
                                        </Empty>
                                    )}
                                </div>
                            </TabsContent>

                            {showReviewTab ? (
                                <TabsContent value="review" className="p-5">
                                    <ReviewPanel
                                        taskId={task.id}
                                        task={task}
                                        enableHotkeys={activeTab === "review"}
                                        className=" bg-[color:var(--surface-1)] p-5 shadow-[var(--soft-shadow)]"
                                    />
                                </TabsContent>
                            ) : null}
                        </Tabs>
                    </Panel>

                    <TaskSidebar task={task} />
                </div>
            </Panel>

            <EditTaskDialog
                open={editOpen}
                onOpenChange={setEditOpen}
                task={task}
            />
            <TaskDeleteDialog
                task={task}
                open={deleteOpen}
                onOpenChange={setDeleteOpen}
                onDeleted={() => {
                    setDeleteOpen(false);
                    navigate("/board");
                }}
            />
        </div>
    );
}

function CriteriaList({
    criteria,
    verdicts,
}: {
    criteria: AcceptanceCriterionResponse[];
    verdicts: ReviewVerdictResponse[] | undefined;
}) {
    if (criteria.length === 0) {
        return (
            <Empty className="min-h-[14rem] border-0">
                <EmptyHeader>
                    <EmptyTitle>No acceptance criteria yet</EmptyTitle>
                    <EmptyDescription>
                        The agent can still work, but review quality will be
                        stronger if you define concrete success checks.
                    </EmptyDescription>
                </EmptyHeader>
            </Empty>
        );
    }
    return (
        <ul className="space-y-1">
            {criteria.map((criterion) => {
                const verdict = verdicts?.find(
                    (v) => v.criterion_id === criterion.id,
                );
                return (
                    <li key={criterion.id}>
                        <Collapsible disabled={!verdict}>
                            <div className="flex items-center gap-2 py-1">
                                {verdict?.verdict === "PASS" ? (
                                    <CheckCircle className="size-3.5 shrink-0 text-[var(--kagan-success)]" />
                                ) : verdict?.verdict === "FAIL" ? (
                                    <XCircle className="size-3.5 shrink-0 text-[var(--destructive)]" />
                                ) : (
                                    <ListChecks className="size-3.5 shrink-0 text-[var(--muted-foreground)]" />
                                )}
                                <span className="min-w-0 flex-1 text-sm text-[var(--muted-foreground)]">
                                    {criterion.text}
                                </span>
                                {verdict ? (
                                    <CollapsibleTrigger asChild>
                                        <Button
                                            variant="ghost"
                                            size="icon-xs"
                                            className="size-5"
                                            aria-label="Toggle verdict details"
                                        >
                                            <ChevronRight className="size-3 transition-transform duration-150 [[data-state=open]_&]:rotate-90" />
                                        </Button>
                                    </CollapsibleTrigger>
                                ) : null}
                            </div>
                            {verdict ? (
                                <CollapsibleContent>
                                    <p className="pb-1 pl-5.5 font-code text-[10px] uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
                                        AI: {verdict.verdict} — {verdict.reason}
                                    </p>
                                </CollapsibleContent>
                            ) : null}
                        </Collapsible>
                    </li>
                );
            })}
        </ul>
    );
}
