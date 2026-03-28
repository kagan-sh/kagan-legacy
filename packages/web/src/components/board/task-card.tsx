import { memo, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import {
    CheckCheck,
    ExternalLink,
    ListChecks,
    Pencil,
    Play,
    Square,
    Terminal,
    Trash2,
} from "lucide-react";
import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { cn } from "@/lib/utils";
import type { WireTask } from "@/lib/api/types";
import { parseUtc } from "@/lib/utils/time";
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
    onStartAgent?: (task: WireTask) => void;
    onStopAgent?: (task: WireTask) => void;
    onAttachTask?: (task: WireTask) => void;
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

function TaskCardBody({
    task,
    isSelected = false,
}: {
    task: WireTask;
    isSelected?: boolean;
}) {
    const criteriaCount = task.acceptance_criteria?.length ?? 0;

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

            <div
                className={cn(
                    "overflow-hidden transition-all duration-150",
                    isSelected
                        ? "max-h-20 opacity-100"
                        : "max-h-0 opacity-0 group-hover:max-h-20 group-hover:opacity-100",
                )}
            >
                <p className="font-code text-[10px] uppercase tracking-[0.16em] text-foreground/60">
                    {task.id}
                </p>

                {task.description ? (
                    <p className="line-clamp-1 text-[11px] leading-4 text-[var(--muted-foreground)]">
                        {task.description}
                    </p>
                ) : null}

                <div className="mt-0.5 flex flex-wrap items-center gap-1">
                    <span className="inline-flex items-center gap-0.5 px-1 py-0 text-[9px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                        <ListChecks className="size-2.5" />
                        {criteriaCount} AC
                    </span>
                    {task.review_approved ? (
                        <span className="inline-flex items-center gap-0.5 px-1 py-0 text-[9px] font-medium uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
                            <CheckCheck className="size-2.5" />
                            Approved
                        </span>
                    ) : null}
                </div>

                <div className="mt-0.5 flex items-center justify-between gap-1 bg-[color:var(--surface-1)] px-2 py-0.5 text-[9px] text-muted-foreground">
                    <span className="inline-flex min-w-0 items-center truncate">
                        {formatLastActivity(
                            task.last_event_at || task.updated_at,
                        )}
                    </span>
                </div>
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
    onStartAgent,
    onStopAgent,
    onAttachTask,
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

    // 2.6: Reset didDrag when dragging ends (including Escape-cancelled drags)
    useEffect(() => {
        if (!isDragging && didDrag.current) {
            // Delay reset so the click handler can still read it for the current event cycle
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
            aria-label={task.title}
            aria-pressed={isSelected}
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

            <TaskCardBody task={task} isSelected={isSelected} />
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
                {task.active_session ? (
                    <DropdownMenuItem onSelect={() => onStopAgent?.(task)}>
                        <Square />
                        Stop Agent
                    </DropdownMenuItem>
                ) : (
                    <DropdownMenuItem onSelect={() => onStartAgent?.(task)}>
                        <Play />
                        Start Agent
                    </DropdownMenuItem>
                )}
                {task.status !== "DONE" ? (
                    <DropdownMenuItem onSelect={() => onAttachTask?.(task)}>
                        <Terminal />
                        Attach
                    </DropdownMenuItem>
                ) : null}
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

function areEqual(prevProps: TaskCardProps, nextProps: TaskCardProps): boolean {
    return (
        prevProps.task.id === nextProps.task.id &&
        prevProps.task.status === nextProps.task.status &&
        prevProps.task.title === nextProps.task.title &&
        prevProps.task.priority === nextProps.task.priority &&
        prevProps.task.active_session?.id === nextProps.task.active_session?.id &&
        prevProps.task.last_event_at === nextProps.task.last_event_at &&
        prevProps.task.review_approved === nextProps.task.review_approved &&
        prevProps.isSelected === nextProps.isSelected &&
        prevProps.onSelectTask === nextProps.onSelectTask &&
        prevProps.onOpenTask === nextProps.onOpenTask &&
        prevProps.onEditTask === nextProps.onEditTask &&
        prevProps.onDeleteTask === nextProps.onDeleteTask &&
        prevProps.onStartAgent === nextProps.onStartAgent &&
        prevProps.onStopAgent === nextProps.onStopAgent &&
        prevProps.onAttachTask === nextProps.onAttachTask &&
        prevProps.onInspectTask === nextProps.onInspectTask &&
        prevProps.className === nextProps.className
    );
}

export const TaskCard = memo(TaskCardImpl, areEqual);
TaskCard.displayName = "TaskCard";
