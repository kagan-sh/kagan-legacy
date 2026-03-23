import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router";
import {
    ArrowLeft,
    CheckCircle,
    ChevronRight,
    LayoutDashboard,
    ListChecks,
    MessageSquare,
    MoveRight,
    Pencil,
    Terminal,
    XCircle,
} from "lucide-react";
import { useSetAtom } from "jotai";
import { toast } from "sonner";
import { apiClient } from "@/lib/api/client";
import type { TaskStatus, WireTask } from "@/lib/api/types";
import { fetchTasksAtom } from "@/lib/atoms/board";
import {
    rightRailChatSessionIdAtom,
    rightRailModeAtom,
    rightRailTaskIdAtom,
} from "@/lib/atoms/ui";
import {
    STATUS_LABELS,
    getAllowedTaskTransitions,
} from "@/lib/utils/constants";
import { useTaskEvents } from "@/lib/hooks/use-task-events";
import {
    openInEditor,
    launcherDisplayName,
} from "@/lib/utils/editor-links";
import {
    ActionEmptyState,
    InspectorSection,
    Panel,
    StickyActionBar,
} from "@/components/shared/workspace";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { AgentControl } from "@/components/board/agent-control";
import { ReviewPanel } from "@/components/board/review-panel";
import { DiffViewer } from "@/components/board/diff-viewer";
import { EditTaskDialog } from "@/components/board/edit-task-dialog";
import { TaskDeleteDialog } from "@/components/board/task-delete-dialog";
import { TaskSidebar } from "@/components/board/task-sidebar";
import { isEditableTarget, hasOpenOverlay } from "@/lib/utils/dom";
import { normalizeLauncher, quoteShell } from "@/lib/utils";

export type WorkspaceTab = "overview" | "changes" | "review";


function tmuxSessionName(sessionId: string): string {
    return `kagan-${sessionId.replaceAll(":", "-")}`;
}

export function defaultTabForTask(task: WireTask): WorkspaceTab {
    if (task.status === "BACKLOG") return "overview";
    if (task.status === "REVIEW" && task.has_workspace) return "review";
    if (task.status === "DONE" && (task.review_verdicts?.length ?? 0) > 0)
        return "review";
    if (task.has_workspace) return "changes";
    return "overview";
}

export function Component() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const fetchTasks = useSetAtom(fetchTasksAtom);
    const setRailMode = useSetAtom(rightRailModeAtom);
    const setRailTaskId = useSetAtom(rightRailTaskIdAtom);
    const setRailChatSessionId = useSetAtom(rightRailChatSessionIdAtom);
    const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
    const [editOpen, setEditOpen] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [userClosedRail, setUserClosedRail] = useState(false);

    const [worktreePath, setWorktreePath] = useState<string | null>(null);
    const [attachedLauncher, setAttachedLauncher] = useState<string | null>(null);

    const { task, loading, runningSince } = useTaskEvents(id, {
        initialLimit: 80,
    });

    // 2.4: Always read tab from URL params — URL is the source of truth
    useEffect(() => {
        if (!task) return;
        const urlTab = searchParams.get("tab");
        if (
            urlTab === "overview" ||
            urlTab === "changes" ||
            urlTab === "review"
        ) {
            setActiveTab(urlTab);
        } else {
            setActiveTab(defaultTabForTask(task));
        }
    }, [task, searchParams]);

    useEffect(() => {
        if (id) {
            setRailTaskId(id);
            setRailChatSessionId(null);
        }
        return () => setRailTaskId(null);
    }, [id, setRailChatSessionId, setRailTaskId]);

    // 2.5: Auto-open chat rail only if user hasn't explicitly closed it
    useEffect(() => {
        if (!id || !task) return;
        if (task.active_session?.launcher) return;
        if (userClosedRail) return;
        if (task.active_session || task.status === "IN_PROGRESS") {
            setRailTaskId(id);
            setRailChatSessionId(null);
            setRailMode("chat-right");
        }
    }, [
        id,
        task?.active_session?.id,
        task?.status,
        userClosedRail,
    ]); // eslint-disable-line react-hooks/exhaustive-deps

    const displayTask = task;

    useEffect(() => {
        if (!id || !displayTask?.active_session?.launcher) {
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
    }, [id, displayTask?.active_session?.launcher]);

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

    const handleOpenTaskChat = useCallback(() => {
        if (!task) return;
        setUserClosedRail(false);
        setRailTaskId(task.id);
        setRailChatSessionId(null);
        setRailMode("chat-right");
    }, [setRailChatSessionId, setRailMode, setRailTaskId, task]);

    const handleAttachAttachedSession = useCallback(async () => {
        if (!displayTask) return;
        if (!displayTask.active_session?.launcher) {
            toast.error("No interactive session to attach");
            return;
        }
        const launcher = normalizeLauncher(
            displayTask.active_session.launcher ??
                displayTask.launcher ??
                attachedLauncher ??
                "vscode",
        );
        const activeSessionId = displayTask.active_session?.id ?? null;

        if (launcher === "tmux") {
            if (!activeSessionId) {
                toast.error("No active session to attach");
                return;
            }
            const command = `tmux attach-session -t ${tmuxSessionName(activeSessionId)}`;
            try {
                await navigator.clipboard.writeText(command);
                toast.success("tmux attach command copied to clipboard");
            } catch {
                toast.info(`Run: ${command}`);
            }
            return;
        }

        if (launcher === "nvim") {
            if (!worktreePath) {
                toast.error("Worktree path not available");
                return;
            }
            const command = `cd ${quoteShell(worktreePath)} && nvim .kagan/start_prompt.md`;
            try {
                await navigator.clipboard.writeText(command);
                toast.success("Neovim command copied to clipboard");
            } catch {
                toast.info(`Run: ${command}`);
            }
            return;
        }

        if (!worktreePath) {
            toast.error("Worktree path not available");
            return;
        }

        const opened = openInEditor(launcher, worktreePath);
        if (opened) {
            toast.success(`Opening ${launcherDisplayName(launcher)}...`);
        } else {
            toast.info(`Open ${launcherDisplayName(launcher)} manually`);
        }
    }, [
        displayTask?.active_session?.id,
        displayTask?.launcher,
        attachedLauncher,
        worktreePath,
    ]);

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

    if (!displayTask) {
        return (
            <div className="mx-auto flex h-full w-full max-w-[1680px] items-center justify-center px-6 py-10">
                <ActionEmptyState
                    title="Task not found"
                    description="The task may have been deleted or the workspace is no longer synced with the server."
                />
            </div>
        );
    }

    const criteria = displayTask.acceptance_criteria ?? [];
    const hasVerdicts = (displayTask.review_verdicts?.length ?? 0) > 0;
    const showReviewTab =
        displayTask.status === "REVIEW" ||
        (displayTask.status === "DONE" && hasVerdicts);

    return (
        <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-5 px-4 py-4 sm:px-6">
            <Breadcrumb>
                <BreadcrumbList className="text-[var(--muted-foreground)]">
                    <BreadcrumbItem>
                        <BreadcrumbLink
                            onClick={() => navigate("/board")}
                            className="inline-flex cursor-pointer items-center gap-1.5 hover:text-[var(--foreground)]"
                        >
                            <LayoutDashboard className="size-3.5" />
                            Board
                        </BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator>
                        <ChevronRight className="size-3.5" />
                    </BreadcrumbSeparator>
                    <BreadcrumbItem>
                        <BreadcrumbPage className="max-w-[200px] truncate text-[var(--foreground)] sm:max-w-[300px]">
                            {displayTask.title}
                        </BreadcrumbPage>
                    </BreadcrumbItem>
                </BreadcrumbList>
            </Breadcrumb>

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
                    {displayTask.title}
                </h1>
                <span className="h-4 w-px bg-[color:var(--border-subtle)]" />
                <span className="text-xs text-[var(--muted-foreground)]">
                    {displayTask.description || "No description"}
                </span>
                <div className="ml-auto flex items-center gap-2">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setEditOpen(true)}
                    >
                        <Pencil className="size-3.5" />
                        Edit
                    </Button>
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setDeleteOpen(true)}
                    >
                        Delete
                    </Button>
                </div>
            </div>

            <Panel className="mt-3">
                <StickyActionBar>
                    <AgentControl
                        taskId={displayTask.id}
                        status={displayTask.status}
                        startedAt={runningSince}
                        buttonSize="sm"
                        worktreePath={worktreePath}
                        attachedLauncher={attachedLauncher}
                        taskLauncher={displayTask.launcher}
                        activeSessionId={displayTask.active_session?.id ?? null}
                        activeSessionLauncher={
                            displayTask.active_session?.launcher ?? null
                        }
                    />
                    <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleOpenTaskChat}
                    >
                        <MessageSquare className="size-4" />
                        Open chat
                    </Button>
                    {displayTask.active_session?.launcher &&
                    displayTask.status === "IN_PROGRESS" ? (
                        <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => {
                                void handleAttachAttachedSession();
                            }}
                        >
                            <Terminal className="size-4" />
                            Attach session
                        </Button>
                    ) : null}
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
                                displayTask.status as TaskStatus,
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
                                            {displayTask.description ||
                                                "No written description yet."}
                                        </p>
                                    </InspectorSection>

                                    <InspectorSection title="Acceptance Criteria">
                                        {criteria.length > 0 ? (
                                            <div className="space-y-2">
                                                {criteria.map(
                                                    (criterion, index) => {
                                                        const verdict =
                                                            displayTask.review_verdicts?.find(
                                                                (v) =>
                                                                    v.criterion_index ===
                                                                    index,
                                                            );
                                                        return (
                                                            <div
                                                                key={criterion}
                                                                className="flex items-start gap-3 bg-[color:var(--surface-1)] p-3 shadow-[var(--soft-shadow)]"
                                                            >
                                                                {verdict?.verdict ===
                                                                "PASS" ? (
                                                                    <CheckCircle className="mt-0.5 size-4 text-[var(--kagan-success)]" />
                                                                ) : verdict?.verdict ===
                                                                  "FAIL" ? (
                                                                    <XCircle className="mt-0.5 size-4 text-[var(--destructive)]" />
                                                                ) : (
                                                                    <ListChecks className="mt-0.5 size-4 text-[var(--primary)]" />
                                                                )}
                                                                <div className="min-w-0 flex-1">
                                                                    <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                                                                        {
                                                                            criterion
                                                                        }
                                                                    </p>
                                                                    {verdict ? (
                                                                        <p className="mt-1 font-code text-[10px] uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
                                                                            AI:{" "}
                                                                            {
                                                                                verdict.verdict
                                                                            }{" "}
                                                                            —{" "}
                                                                            {
                                                                                verdict.reason
                                                                            }
                                                                        </p>
                                                                    ) : null}
                                                                </div>
                                                            </div>
                                                        );
                                                    },
                                                )}
                                            </div>
                                        ) : (
                                            <ActionEmptyState
                                                title="No acceptance criteria yet"
                                                description="The agent can still work, but review quality will be stronger if you define concrete success checks."
                                                className="min-h-[14rem]"
                                            />
                                        )}
                                    </InspectorSection>
                                </div>
                            </TabsContent>

                            <TabsContent value="changes" className="p-5">
                                <div className="grid gap-4">
                                    {displayTask.has_workspace ? (
                                        <DiffViewer
                                            taskId={displayTask.id}
                                            taskStatus={displayTask.status}
                                        />
                                    ) : displayTask.status === "DONE" ? (
                                        <ActionEmptyState
                                            title="Changes merged"
                                            description="This task's branch has been merged and the workspace cleaned up. The diff is no longer available."
                                        />
                                    ) : (
                                        <ActionEmptyState
                                            title="Workspace not ready"
                                            description="Provision or start the task to let Kagan create a working tree. Once code starts moving, diffs will appear here."
                                        />
                                    )}
                                </div>
                            </TabsContent>

                            {showReviewTab ? (
                                <TabsContent value="review" className="p-5">
                                    <ReviewPanel
                                        taskId={displayTask.id}
                                        task={displayTask}
                                        enableHotkeys={activeTab === "review"}
                                        className=" bg-[color:var(--surface-1)] p-5 shadow-[var(--soft-shadow)]"
                                    />
                                </TabsContent>
                            ) : null}
                        </Tabs>
                    </Panel>

                    <TaskSidebar task={displayTask} />
                </div>
            </Panel>

            <EditTaskDialog
                open={editOpen}
                onOpenChange={setEditOpen}
                task={displayTask}
            />
            <TaskDeleteDialog
                task={displayTask}
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
