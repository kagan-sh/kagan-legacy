import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router";
import {
    CheckCircle,
    ChevronLeft,
    ChevronRight,
    GitBranch,
    ListChecks,
    MessageSquare,
    MoveRight,
    Pencil,
    XCircle,
} from "lucide-react";
import { useAtomValue, useSetAtom } from "jotai";
import { toast } from "sonner";
import { apiClient } from "@/lib/api/client";
import type {
    AcceptanceCriterionResponse,
    ReviewVerdictResponse,
    TaskStatus,
    WireTask,
    WireTaskSession,
} from "@kagan/shared-api-client";
import { taskSessionLane, type TaskSessionLane } from "@/lib/sessions/kind";
import { cn } from "@/lib/utils";
import { fetchTasksAtom } from "@/lib/atoms/board";
import { shellTabAtom } from "@/lib/atoms/shell";
import {
    STATUS_LABELS,
    getAllowedTaskTransitions,
} from "@/lib/utils/constants";
import { useTaskEvents } from "@/lib/hooks/use-task-events";
import { useSessionOverlay } from "@/lib/hooks/use-session-overlay";
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription } from "@/components/ui/empty";
import { Button } from "@/components/ui/button";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
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

/**
 * Default tab selection logic based on task state:
 * - BACKLOG: always Overview (no workspace yet)
 * - REVIEW + workspace: Review tab (primary action needed)
 * - DONE + approved: Review tab (show approved state)
 * - workspace present: Changes tab (code is the story)
 * - fallback: Overview
 */
export function defaultTabForTask(task: WireTask): WorkspaceTab {
    if (task.status === "BACKLOG") return "overview";
    if (task.status === "REVIEW" && task.has_workspace) return "review";
    if (task.status === "DONE" && task.review_approved) return "review";
    if (task.has_workspace) return "changes";
    return "overview";
}

/** Map task status to design `data-mode` values for the status pill. */
function statusDataMode(status: string): string {
    if (status === "IN_PROGRESS") return "RUN";
    if (status === "REVIEW") return "REVIEW";
    if (status === "DONE") return "DONE";
    return "BACKLOG";
}

/** Short, readable task ID chip — first 8 chars of UUID. */
function shortId(id: string): string {
    return id.slice(0, 8);
}

export function Component() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const fetchTasks = useSetAtom(fetchTasksAtom);
    const shellTab = useAtomValue(shellTabAtom);
    const overlay = useSessionOverlay();
    const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
    const [editOpen, setEditOpen] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);

    const [worktreePath, setWorktreePath] = useState<string | null>(null);
    const [attachedLauncher, setAttachedLauncher] = useState<string | null>(null);
    const [taskSessions, setTaskSessions] = useState<WireTaskSession[]>([]);

    const { task, loading, runningSince } = useTaskEvents(id, {
        initialLimit: 80,
    });

    // Set initial tab from URL param or task status — only on first load / task change.
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
                if (!cancelled) setWorktreePath(res.worktree?.path ?? null);
            },
            () => {
                if (!cancelled) setWorktreePath(null);
            },
        );

        void apiClient.getSettings().then(
            (settings) => {
                if (!cancelled) setAttachedLauncher(settings.attached_launcher ?? null);
            },
            () => {
                if (!cancelled) setAttachedLauncher(null);
            },
        );

        return () => { cancelled = true; };
    }, [id, task?.active_session?.launcher]);

    // Fetch task sessions once on mount (or when the task id changes) to determine
    // available lanes for the segmented control in the header.
    useEffect(() => {
        if (!id) return;
        const controller = new AbortController();
        void apiClient.getTaskSessions(id).then(
            (sessions) => {
                if (!controller.signal.aborted) setTaskSessions(sessions);
            },
            () => {
                if (!controller.signal.aborted) setTaskSessions([]);
            },
        );
        return () => { controller.abort(); };
    }, [id]);

    // Derive available lanes from fetched sessions.
    const availableLanes = new Set(
        taskSessions.map(taskSessionLane).filter((l): l is TaskSessionLane => l !== null),
    );
    const hasMultipleLanes = availableLanes.has("worker") && availableLanes.has("reviewer");

    // Read the active lane from the URL search param.
    const activeLane = ((): TaskSessionLane | null => {
        const raw = searchParams.get("lane");
        if (raw === "worker" || raw === "reviewer") return raw;
        return null;
    })();

    const handleLaneSelect = (lane: TaskSessionLane) => {
        setSearchParams((prev) => {
            const next = new URLSearchParams(prev);
            next.set("lane", lane);
            return next;
        });
    };

    const handleTransition = async (status: TaskStatus) => {
        if (!id) return;
        try {
            await apiClient.transitionTaskStatus(id, status);
            fetchTasks();
            toast.success(`Moved to ${STATUS_LABELS[status]}`);
        } catch (error) {
            toast.error(error instanceof Error ? error.message : "Failed to transition");
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
                toast.error("No session found for this task");
            }
        } catch (error) {
            toast.error(error instanceof Error ? error.message : "Failed to load sessions");
        }
    }, [id, task, overlay]);

    // Auto-open session overlay when ?lane=worker or ?lane=review is present.
    const laneAutoOpenedRef = useRef(false);
    useEffect(() => {
        if (!task || !id) return;
        if (laneAutoOpenedRef.current) return;
        const lane = searchParams.get("lane");
        if (!lane || (lane !== "worker" && lane !== "review")) return;
        if (task.active_session?.id) {
            laneAutoOpenedRef.current = true;
            void handleOpenSession();
        }
    }, [id, task, searchParams, handleOpenSession]);

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            if (editOpen || deleteOpen || hasOpenOverlay()) return;
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
            <div className="flex h-full w-full items-center justify-center">
                <div className="h-10 w-48 animate-pulse rounded bg-[var(--surface-2)]" />
            </div>
        );
    }

    if (!task) {
        return (
            <div className="flex h-full w-full items-center justify-center">
                <Empty className="border-0">
                    <EmptyHeader>
                        <EmptyTitle>Task not found</EmptyTitle>
                        <EmptyDescription>
                            The task may have been deleted or the workspace is no longer synced with the server.
                        </EmptyDescription>
                    </EmptyHeader>
                </Empty>
            </div>
        );
    }

    const criteria = task.acceptance_criteria ?? [];
    const diffFileCount = task.diff_summary?.files_changed ?? 0;
    const criteriaCount = criteria.filter((c) => c.text.trim()).length;
    const showReviewTab =
        task.status === "REVIEW" || (task.status === "DONE" && task.review_approved);

    // Derive the "back" label from shellTab — workspace → "Workspace", kanban → "Board".
    const backLabel = shellTab === "workspace" ? "Workspace" : "Board";
    const backPath = shellTab === "workspace" ? "/chat" : "/board";

    const dataMode = statusDataMode(task.status);
    const allowedTransitions = getAllowedTaskTransitions(task.status as TaskStatus);

    return (
        /* tv — full-height grid: head 50px + action 46px + body 1fr */
        <div
            className="tv grid h-full overflow-hidden"
            style={{
                gridTemplateRows: "50px 46px 1fr",
                background: "var(--background)",
            }}
        >
            {/* ── A. Task view header (tv-head) ─────────────────────────────── */}
            <header
                className="tv-head flex items-center gap-2.5 border-b px-[18px]"
                style={{
                    borderColor: "var(--border)",
                    background: "linear-gradient(180deg, var(--surface-1), var(--background))",
                }}
            >
                {/* Back button */}
                <button
                    type="button"
                    onClick={() => navigate(backPath)}
                    aria-label={`Back to ${backLabel}`}
                    className="tv-back inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-[5px] border px-[9px] py-1 font-mono text-[11px] transition-colors"
                    style={{
                        height: 27,
                        color: "var(--muted-foreground)",
                        borderColor: "var(--border)",
                        background: "transparent",
                    }}
                >
                    <ChevronLeft className="size-[11px]" aria-hidden="true" />
                    {backLabel}
                </button>

                {/* Task ID chip */}
                <span
                    className="shrink-0 font-mono text-[11px]"
                    style={{ color: "var(--muted-foreground)" }}
                    aria-label={`Task ID: ${task.id}`}
                >
                    {shortId(task.id)}
                </span>

                {/* Title */}
                <h1
                    className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-medium"
                    style={{ color: "var(--foreground)" }}
                >
                    {task.title}
                </h1>

                {/* Branch indicator */}
                {task.base_branch ? (
                    <span
                        className="hidden shrink-0 items-center gap-1 font-mono text-[11px] sm:inline-flex"
                        style={{ color: "var(--muted-foreground)" }}
                        aria-label={`Branch: task-${shortId(task.id)} into ${task.base_branch}`}
                    >
                        <GitBranch className="size-[11px]" aria-hidden="true" />
                        task-{shortId(task.id)} → {task.base_branch}
                    </span>
                ) : null}

                {/* Status pill */}
                <span
                    className="tv-status shrink-0 cursor-default rounded-[4px] border px-[9px] py-[3px] font-mono text-[11px]"
                    data-mode={dataMode}
                    style={statusPillStyle(dataMode)}
                    aria-label={`Status: ${STATUS_LABELS[task.status] ?? task.status}`}
                >
                    {STATUS_LABELS[task.status] ?? task.status}
                </span>

                {/* Lane segmented control — only when both worker + reviewer sessions exist */}
                {hasMultipleLanes ? (
                    <LaneControl
                        activeLane={activeLane}
                        onSelect={handleLaneSelect}
                    />
                ) : null}

                {/* Edit chip button */}
                <button
                    type="button"
                    onClick={() => setEditOpen(true)}
                    aria-label="Edit task"
                    className="tv-edit inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-[5px] border px-[9px] py-1 text-[12px] transition-colors"
                    style={{
                        height: 27,
                        fontFamily: "var(--font-ui)",
                        color: "var(--muted-foreground)",
                        borderColor: "var(--border)",
                        background: "transparent",
                    }}
                >
                    <Pencil className="size-3" aria-hidden="true" />
                    Edit
                </button>
            </header>

            {/* ── B. Task action bar (tv-action) ────────────────────────────── */}
            <div
                className="tv-action flex items-center gap-2 border-b px-[18px]"
                style={{
                    borderColor: "var(--border)",
                    background: "var(--surface-1)",
                }}
            >
                {/* Primary Run / Stop via AgentControl */}
                <AgentControl
                    taskId={task.id}
                    status={task.status}
                    startedAt={runningSince}
                    buttonSize="sm"
                    worktreePath={worktreePath}
                    attachedLauncher={attachedLauncher}
                    taskLauncher={task.launcher}
                    activeSessionId={task.active_session?.id ?? null}
                    activeSessionLauncher={task.active_session?.launcher ?? null}
                />

                {/* Open chat / session */}
                <button
                    type="button"
                    onClick={handleOpenSession}
                    aria-label="Open session chat"
                    className="tvbtn inline-flex cursor-pointer items-center gap-1.5 rounded-[5px] border font-medium transition-colors"
                    style={tvBtnStyle()}
                >
                    <MessageSquare className="size-[13px]" aria-hidden="true" />
                    Open chat
                </button>

                {/* Move to… — right-aligned via ml-auto */}
                {allowedTransitions.length > 0 ? (
                    <div className="ml-auto">
                        <Select
                            value=""
                            onValueChange={(value) => handleTransition(value as TaskStatus)}
                        >
                            <SelectTrigger
                                aria-label="Move task to another status"
                                size="sm"
                                className="h-7 gap-1.5 rounded-[5px] border px-3 text-xs font-medium"
                                style={{
                                    borderColor: "var(--border)",
                                    background: "var(--surface-2)",
                                    color: "var(--muted-foreground)",
                                }}
                            >
                                <MoveRight className="size-[13px]" aria-hidden="true" />
                                <SelectValue placeholder="Move to…" />
                            </SelectTrigger>
                            <SelectContent>
                                {allowedTransitions.map((status) => (
                                    <SelectItem key={status} value={status}>
                                        {STATUS_LABELS[status]}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                ) : null}
            </div>

            {/* ── C. Task body grid (tv-body) ───────────────────────────────── */}
            <div
                className="tv-body grid min-h-0 overflow-hidden"
                style={{ gridTemplateColumns: "1fr 264px" }}
            >
                {/* Left column: tab bar + scrolling content */}
                <div
                    className="tv-main grid min-h-0 overflow-hidden border-r"
                    style={{
                        gridTemplateRows: "44px 1fr",
                        borderColor: "var(--border)",
                    }}
                >
                    {/* Tab bar */}
                    <div
                        className="tv-tabs-bar flex items-center border-b px-5"
                        style={{
                            borderColor: "var(--border)",
                            background: "var(--surface-1)",
                        }}
                        role="tablist"
                        aria-label="Task sections"
                    >
                        <TvTab
                            label="Overview"
                            active={activeTab === "overview"}
                            onClick={() => setActiveTab("overview")}
                        />
                        <TvTab
                            label="Changes"
                            active={activeTab === "changes"}
                            badge={diffFileCount > 0 ? String(diffFileCount) : undefined}
                            onClick={() => setActiveTab("changes")}
                        />
                        {showReviewTab ? (
                            <TvTab
                                label="Review"
                                active={activeTab === "review"}
                                badge={criteriaCount > 0 ? String(criteriaCount) : undefined}
                                onClick={() => setActiveTab("review")}
                            />
                        ) : null}
                    </div>

                    {/* Scrolling tab content */}
                    <div
                        className="tv-content overflow-y-auto px-7 py-6"
                        role="tabpanel"
                        aria-label={activeTab}
                        id={`tv-tab-${activeTab}`}
                    >
                        {activeTab === "overview" ? (
                            <OverviewContent task={task} criteria={criteria} />
                        ) : activeTab === "changes" ? (
                            <ChangesContent task={task} />
                        ) : activeTab === "review" && showReviewTab ? (
                            <ReviewPanel
                                taskId={task.id}
                                task={task}
                                enableHotkeys={activeTab === "review"}
                            />
                        ) : null}
                    </div>
                </div>

                {/* Right sidebar */}
                <aside
                    className="tv-sidebar overflow-y-auto px-[18px] py-5"
                    style={{ background: "var(--surface-1)" }}
                    aria-label="Task metadata"
                >
                    <TaskSidebar task={task} />
                </aside>
            </div>

            {/* Dialogs */}
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

// ──────────────────────────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Segmented control for switching between Worker and Reviewer session lanes.
 * Mirrors the Board/List toggle in `board-toolbar.tsx` — mono font, uppercase,
 * hairline outer border, no border between segments, background fill for active.
 *
 * Exported for focused unit tests.
 */
export function LaneControl({
    activeLane,
    onSelect,
}: {
    activeLane: TaskSessionLane | null;
    onSelect: (lane: TaskSessionLane) => void;
}) {
    const lanes: TaskSessionLane[] = ["worker", "reviewer"];
    return (
        <div
            role="group"
            aria-label="Session lane"
            className="inline-flex shrink-0 overflow-hidden rounded-[5px] border"
            style={{ borderColor: "var(--border)", background: "var(--surface-1)" }}
        >
            {lanes.map((lane) => {
                const isActive = activeLane === lane;
                return (
                    <button
                        key={lane}
                        type="button"
                        aria-pressed={isActive}
                        aria-label={lane === "worker" ? "Worker session" : "Reviewer session"}
                        onClick={() => onSelect(lane)}
                        className={cn(
                            "cursor-pointer border-0 font-mono text-[10.5px] uppercase tracking-[0.18em]",
                        )}
                        style={{
                            padding: "4px 10px",
                            background: isActive ? "var(--surface-3)" : "transparent",
                            color: isActive ? "var(--foreground)" : "var(--muted-foreground)",
                        }}
                    >
                        {lane === "worker" ? "Worker" : "Reviewer"}
                    </button>
                );
            })}
        </div>
    );
}

function TvTab({
    label,
    active,
    badge,
    onClick,
}: {
    label: string;
    active: boolean;
    badge?: string;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            role="tab"
            aria-selected={active}
            data-state={active ? "active" : "inactive"}
            onClick={onClick}
            className="tvtab flex cursor-pointer items-center gap-1.5 border-0 px-3.5 text-[12.5px] font-normal transition-colors"
            style={{
                height: 44,
                fontFamily: "var(--font-ui)",
                color: active ? "var(--primary)" : "var(--muted-foreground)",
                borderBottom: active
                    ? "2px solid var(--primary)"
                    : "2px solid transparent",
                marginBottom: -1,
                background: "transparent",
            }}
        >
            {label}
            {badge !== undefined ? (
                <span
                    className="cnt rounded-[3px] px-[5px] py-[1px] font-mono text-[9.5px] tracking-[0.04em]"
                    style={
                        active
                            ? {
                                  background: "rgba(212,168,75,0.14)",
                                  color: "var(--primary)",
                              }
                            : {
                                  background: "var(--surface-3)",
                                  color: "var(--muted-foreground)",
                              }
                    }
                >
                    {badge}
                </span>
            ) : null}
        </button>
    );
}

function OverviewContent({
    task,
    criteria,
}: {
    task: WireTask;
    criteria: AcceptanceCriterionResponse[];
}) {
    return (
        <div className="tv-sec space-y-7">
            <section className="tv-sec">
                <p
                    className="tv-sec-label mb-3 font-mono text-[10px] uppercase tracking-[0.18em]"
                    style={{ color: "var(--muted-foreground)" }}
                >
                    Description
                </p>
                <p
                    className="tv-desc text-[13px] leading-[1.75]"
                    style={{ color: "var(--muted-foreground)" }}
                >
                    {task.description || "No written description yet."}
                </p>
            </section>

            <section className="tv-sec">
                <p
                    className="tv-sec-label mb-3 font-mono text-[10px] uppercase tracking-[0.18em]"
                    style={{ color: "var(--muted-foreground)" }}
                >
                    Acceptance Criteria
                </p>
                <CriteriaList criteria={criteria} verdicts={task.review_verdicts} />
            </section>
        </div>
    );
}

function ChangesContent({ task }: { task: WireTask }) {
    if (task.has_workspace) {
        return <DiffViewer taskId={task.id} taskStatus={task.status} />;
    }
    if (task.status === "DONE") {
        return (
            <Empty className="border-0">
                <EmptyHeader>
                    <EmptyTitle>Changes merged</EmptyTitle>
                    <EmptyDescription>
                        This task&apos;s branch has been merged and the workspace cleaned up.
                        The diff is no longer available.
                    </EmptyDescription>
                </EmptyHeader>
            </Empty>
        );
    }
    return (
        <Empty className="border-0">
            <EmptyHeader>
                <EmptyTitle>Workspace not ready</EmptyTitle>
                <EmptyDescription>
                    Provision or start the task to let Kagan create a working tree.
                    Once code starts moving, diffs will appear here.
                </EmptyDescription>
            </EmptyHeader>
        </Empty>
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
            <Empty className="min-h-[10rem] border-0">
                <EmptyHeader>
                    <EmptyTitle>No acceptance criteria yet</EmptyTitle>
                    <EmptyDescription>
                        The agent can still work, but review quality will be stronger if you
                        define concrete success checks.
                    </EmptyDescription>
                </EmptyHeader>
            </Empty>
        );
    }
    return (
        <ul className="criteria-list flex flex-col gap-1.5">
            {criteria.map((criterion) => {
                const verdict = verdicts?.find((v) => v.criterion_id === criterion.id);
                const state =
                    verdict?.verdict === "PASS"
                        ? "pass"
                        : verdict?.verdict === "FAIL"
                          ? "fail"
                          : "pending";

                return (
                    <li key={criterion.id}>
                        <Collapsible disabled={!verdict}>
                            <div
                                className="criteria-item flex items-start gap-2.5 rounded-[5px] border px-3.5 py-2.5 transition-colors"
                                style={{
                                    borderColor:
                                        state === "pass"
                                            ? "rgba(63,181,142,0.22)"
                                            : state === "fail"
                                              ? "rgba(232,85,53,0.22)"
                                              : "var(--border)",
                                    background: "var(--surface-1)",
                                }}
                            >
                                <span className="ci-icon mt-0.5 shrink-0 text-[13px]">
                                    {state === "pass" ? (
                                        <CheckCircle
                                            className="size-3.5"
                                            style={{ color: "var(--kagan-rail-running)" }}
                                            aria-hidden="true"
                                        />
                                    ) : state === "fail" ? (
                                        <XCircle
                                            className="size-3.5"
                                            style={{ color: "#e85535" }}
                                            aria-hidden="true"
                                        />
                                    ) : (
                                        <ListChecks
                                            className="size-3.5"
                                            style={{ color: "var(--muted-foreground)" }}
                                            aria-hidden="true"
                                        />
                                    )}
                                </span>
                                <span
                                    className="ci-text min-w-0 flex-1 text-[12.5px] leading-[1.55]"
                                    style={{ color: "var(--muted-foreground)" }}
                                >
                                    {criterion.text}
                                </span>
                                {verdict ? (
                                    <>
                                        <span
                                            className="ci-verdict self-center rounded-[3px] px-1.5 py-[2px] font-mono text-[9.5px] tracking-[0.1em]"
                                            style={
                                                state === "pass"
                                                    ? {
                                                          color: "var(--kagan-rail-running)",
                                                          background: "rgba(63,181,142,0.12)",
                                                      }
                                                    : state === "fail"
                                                      ? {
                                                            color: "#e85535",
                                                            background: "rgba(232,85,53,0.10)",
                                                        }
                                                      : {
                                                            color: "var(--muted-foreground)",
                                                            background: "var(--surface-2)",
                                                        }
                                            }
                                        >
                                            {verdict.verdict}
                                        </span>
                                        <CollapsibleTrigger asChild>
                                            <Button
                                                variant="ghost"
                                                size="icon-xs"
                                                className="size-5 shrink-0"
                                                aria-label="Toggle verdict details"
                                            >
                                                <ChevronRight className="size-3 transition-transform duration-150 [[data-state=open]_&]:rotate-90" />
                                            </Button>
                                        </CollapsibleTrigger>
                                    </>
                                ) : null}
                            </div>
                            {verdict ? (
                                <CollapsibleContent>
                                    <p className="pb-1 pl-6 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
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

// ──────────────────────────────────────────────────────────────────────────────
// Style helpers — inline styles that match CSS custom properties from the design
// ──────────────────────────────────────────────────────────────────────────────

function statusPillStyle(mode: string): React.CSSProperties {
    switch (mode) {
        case "RUN":
            return {
                color: "var(--kagan-rail-warning)",
                background: "rgba(230,192,123,0.10)",
                borderColor: "rgba(230,192,123,0.20)",
            };
        case "REVIEW":
            return {
                color: "var(--kagan-rail-review)",
                background: "rgba(194,124,78,0.10)",
                borderColor: "rgba(194,124,78,0.22)",
            };
        case "DONE":
            return {
                color: "var(--kagan-rail-running)",
                background: "rgba(63,181,142,0.10)",
                borderColor: "rgba(63,181,142,0.22)",
            };
        default: // BACKLOG
            return {
                color: "var(--muted-foreground)",
                background: "var(--surface-2)",
                borderColor: "var(--border)",
            };
    }
}

function tvBtnStyle(): React.CSSProperties {
    return {
        height: 28,
        padding: "0 12px",
        fontSize: 12,
        fontFamily: "var(--font-ui)",
        fontWeight: 500,
        borderRadius: 5,
        borderColor: "var(--border)",
        background: "var(--surface-2)",
        color: "var(--muted-foreground)",
    };
}
