import { memo, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import {
    ExternalLink,
    Pencil,
    Trash2,
} from "lucide-react";
import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { cn } from "@/lib/utils";
import type { WireDiffSummary, WireTask } from "@/lib/api/types";
import { parseUtc } from "@/lib/utils/time";
import { CardPulse } from "@/components/board/card-pulse";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface TaskCardProps {
    task: WireTask;
    className?: string;
    onInspectTask?: (task: WireTask) => void;
    onSelectTask?: (task: WireTask) => void;
    onOpenTask?: (task: WireTask) => void;
    onEditTask?: (task: WireTask) => void;
    onDeleteTask?: (task: WireTask) => void;
    isSelected?: boolean;
}

interface TaskCardOverlayPreviewProps {
    task: WireTask;
    className?: string;
}

const PRIORITY_RAIL: Record<string, string> = {
    LOW: "bg-[color:var(--priority-low-background)]",
    MEDIUM: "bg-[color:var(--priority-medium-background)]",
    HIGH: "bg-[color:var(--priority-high-background)]",
    CRITICAL: "bg-[color:var(--priority-high-background)]",
};

function formatLastActivity(value?: string | null) {
    if (!value) return "No activity";
    const date = parseUtc(value);
    const diffMs = date.getTime() - Date.now();
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    const absMs = Math.abs(diffMs);

    if (absMs < 45_000) return "Just now";
    if (absMs < 3_600_000)
        return rtf.format(Math.round(diffMs / 60_000), "minute");
    if (absMs < 86_400_000)
        return rtf.format(Math.round(diffMs / 3_600_000), "hour");
    if (absMs < 604_800_000)
        return rtf.format(Math.round(diffMs / 86_400_000), "day");

    return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function DiffSummaryRow({
    summary,
    onNavigate,
}: {
    summary: WireDiffSummary;
    onNavigate: (e: React.MouseEvent) => void;
}) {
    const hasChanges =
        summary.files_changed > 0 || summary.additions > 0 || summary.deletions > 0;
    if (!hasChanges) return null;

    return (
        <button
            type="button"
            data-testid="diff-summary"
            onClick={onNavigate}
            className="mt-0.5 flex items-center gap-1.5 text-[10px] tabular-nums leading-none"
            aria-label={`Diff: +${summary.additions} -${summary.deletions} across ${summary.files_changed} file${summary.files_changed === 1 ? "" : "s"}`}
        >
            <span className="text-[color:var(--color-green-600)] dark:text-[color:var(--color-green-400)]">
                +{summary.additions}
            </span>
            <span className="text-[color:var(--color-red-600)] dark:text-[color:var(--color-red-400)]">
                -{summary.deletions}
            </span>
            <span className="text-muted-foreground">
                · {summary.files_changed} file{summary.files_changed === 1 ? "" : "s"}
            </span>
        </button>
    );
}

function TaskCardBody({
    task,
    isSelected = false,
    onDiffNavigate,
}: {
    task: WireTask;
    isSelected?: boolean;
    onDiffNavigate?: (e: React.MouseEvent) => void;
}) {
    return (
        <div className="ml-2 flex min-h-0 flex-col gap-0.5">
            <div className="flex items-center justify-between gap-2">
                <p className="line-clamp-1 text-[0.84rem] font-semibold leading-4 text-[color:var(--foreground)]">
                    {task.title}
                </p>
                {task.active_session ? (
                    <span className="inline-flex shrink-0 items-center gap-1 text-[color:var(--foreground)]" data-testid="live-indicator">
                        <span
                            className="size-1.5 animate-pulse rounded-full bg-[var(--primary)]"
                            aria-hidden="true"
                        />
                    </span>
                ) : null}
            </div>
            <CardPulse
                sessionId={task.active_session?.id ?? null}
                status={task.status}
                startedAt={task.active_session?.started_at ?? null}
                taskTitle={task.title}
            />

            {task.diff_summary && onDiffNavigate ? (
                <DiffSummaryRow summary={task.diff_summary} onNavigate={onDiffNavigate} />
            ) : null}

            <div>
                {task.description ? (
                    <p className="line-clamp-2 text-[11px] leading-4 text-[var(--muted-foreground)]">
                        {task.description}
                    </p>
                ) : null}

                <p className="mt-0.5 text-[9px] text-muted-foreground">
                    {formatLastActivity(task.last_event_at || task.updated_at)}
                </p>
            </div>
        </div>
    );
}

export function TaskCardOverlayPreview({
    task,
    className,
}: TaskCardOverlayPreviewProps) {
    return (
        <div
            className={cn(
                "group relative min-h-[3.5rem] w-full overflow-hidden border border-border bg-card px-3 py-2 text-left shadow-lg",
                className,
            )}
            role="presentation"
            aria-hidden="true"
        >
            <span
                className={cn(
                    "absolute inset-y-0 left-0 w-1 ",
                    PRIORITY_RAIL[task.priority] ?? PRIORITY_RAIL.MEDIUM,
                )}
            />
            <TaskCardBody task={task} isSelected={true} />
        </div>
    );
}


function TaskCardImpl({
    task,
    className,
    onInspectTask,
    onSelectTask,
    onOpenTask,
    onEditTask,
    onDeleteTask,
    isSelected = false,
}: TaskCardProps) {
    const navigate = useNavigate();
    const didDrag = useRef(false);
    const [contextMenuOpen, setContextMenuOpen] = useState(false);
    const { attributes, listeners, setNodeRef, transform, isDragging } =
        useDraggable({
            id: task.id,
        });

    const style = transform
        ? { transform: CSS.Translate.toString(transform) }
        : undefined;

    // Reset didDrag when dragging ends (including Escape-cancelled drags)
    useEffect(() => {
        if (!isDragging && didDrag.current) {
            const id = requestAnimationFrame(() => {
                didDrag.current = false;
            });
            return () => cancelAnimationFrame(id);
        }
    }, [isDragging]);

    if (isDragging) {
        didDrag.current = true;
    }

    const handleOpen = () => {
        if (onOpenTask) {
            onOpenTask(task);
            return;
        }

        if (onInspectTask) {
            onInspectTask(task);
            return;
        }

        navigate(`/task/${task.id}`);
    };

    const handleDiffNavigate = (e: React.MouseEvent) => {
        e.stopPropagation();
        navigate(`/task/${task.id}`, { state: { tab: "diff" } });
    };

    const handleClick = () => {
        if (didDrag.current) {
            didDrag.current = false;
            return;
        }

        if (onSelectTask) {
            onSelectTask(task);
            return;
        }

        handleOpen();
    };

    const cardContent = (
        <div
            ref={setNodeRef}
            style={style}
            {...listeners}
            {...attributes}
            onClick={handleClick}
            onDoubleClick={handleOpen}
            onFocus={() => onSelectTask?.(task)}
            onContextMenu={(e) => {
                e.preventDefault();
                setContextMenuOpen(true);
            }}
            className={cn(
                "group relative min-h-[3.5rem] w-full cursor-grab overflow-hidden border border-border/50 bg-card px-3 py-2 text-left transition-all duration-150 hover:border-border hover:bg-[color:var(--surface-2)] active:cursor-grabbing",
                isSelected &&
                    "ring-1 ring-[var(--primary)]/50 border-[var(--primary)]/30 bg-[color:var(--surface-2)]",
                isDragging && "opacity-0",
                className,
            )}
            role="button"
            tabIndex={0}
            aria-label={isSelected ? `${task.title} (selected)` : task.title}
            aria-current={isSelected ? true : undefined}
            data-task-id={task.id}
            onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleOpen();
                }
            }}
        >
            <span
                className={cn(
                    "absolute inset-y-0 left-0 w-1 ",
                    PRIORITY_RAIL[task.priority] ?? PRIORITY_RAIL.MEDIUM,
                )}
                aria-hidden="true"
            />

            <TaskCardBody task={task} isSelected={isSelected} onDiffNavigate={handleDiffNavigate} />
        </div>
    );

    return (
        <DropdownMenu open={contextMenuOpen} onOpenChange={setContextMenuOpen}>
            <DropdownMenuTrigger asChild>{cardContent}</DropdownMenuTrigger>
            <DropdownMenuContent align="start">
                <DropdownMenuItem onSelect={handleOpen}>
                    <ExternalLink />
                    Open
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => onEditTask?.(task)}>
                    <Pencil />
                    Edit
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                    variant="destructive"
                    onSelect={() => onDeleteTask?.(task)}
                >
                    <Trash2 />
                    Delete
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}

function diffSummaryEqual(
    a: WireDiffSummary | null | undefined,
    b: WireDiffSummary | null | undefined,
): boolean {
    if (a === b) return true;
    if (!a || !b) return false;
    return (
        a.files_changed === b.files_changed &&
        a.additions === b.additions &&
        a.deletions === b.deletions
    );
}

function areEqual(prevProps: TaskCardProps, nextProps: TaskCardProps): boolean {
    return (
        prevProps.task.id === nextProps.task.id &&
        prevProps.task.status === nextProps.task.status &&
        prevProps.task.title === nextProps.task.title &&
        prevProps.task.description === nextProps.task.description &&
        prevProps.task.priority === nextProps.task.priority &&
        prevProps.task.active_session?.id === nextProps.task.active_session?.id &&
        prevProps.task.active_session?.started_at ===
            nextProps.task.active_session?.started_at &&
        prevProps.task.last_event_at === nextProps.task.last_event_at &&
        diffSummaryEqual(prevProps.task.diff_summary, nextProps.task.diff_summary) &&
        prevProps.isSelected === nextProps.isSelected &&
        prevProps.onSelectTask === nextProps.onSelectTask &&
        prevProps.onOpenTask === nextProps.onOpenTask &&
        prevProps.onEditTask === nextProps.onEditTask &&
        prevProps.onDeleteTask === nextProps.onDeleteTask &&
        prevProps.onInspectTask === nextProps.onInspectTask &&
        prevProps.className === nextProps.className
    );
}

export const TaskCard = memo(TaskCardImpl, areEqual);
TaskCard.displayName = "TaskCard";
