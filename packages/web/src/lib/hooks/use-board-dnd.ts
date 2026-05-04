import { useState, useCallback } from "react";
import {
    PointerSensor,
    pointerWithin,
    type DragCancelEvent,
    type DragEndEvent,
    type DragOverEvent,
    type DragStartEvent,
    useSensor,
    useSensors,
} from "@dnd-kit/core";
import type { TaskStatus, WireTask } from "@kagan/shared-api-client";
import {
    COLUMN_ORDER,
    STATUS_LABELS,
    ALLOWED_TASK_TRANSITIONS,
    isAllowedTaskTransition,
} from "@/lib/utils/constants";
import { apiClient } from "@/lib/api/client";
import { toast } from "sonner";

interface UseBoardDndOptions {
    tasks: WireTask[];
    grouped: Record<TaskStatus, WireTask[]>;
    fetchTasks: () => void;
}

interface UseBoardDndReturn {
    activeTask: WireTask | null;
    liveTasksByStatus: Record<TaskStatus, WireTask[]>;
    sensors: ReturnType<typeof useSensors>;
    collisionDetection: typeof pointerWithin;
    handleDragStart: (e: DragStartEvent) => void;
    handleDragOver: (e: DragOverEvent) => void;
    handleDragEnd: (e: DragEndEvent) => void;
    handleDragCancel: (e: DragCancelEvent) => void;
    validDropTargets: Set<TaskStatus>;
    isDragActive: boolean;
}

export function useBoardDnd({
    tasks,
    grouped,
    fetchTasks,
}: UseBoardDndOptions): UseBoardDndReturn {
    const [activeTask, setActiveTask] = useState<WireTask | null>(null);
    const [dragState, setDragState] = useState<Record<
        TaskStatus,
        WireTask[]
    > | null>(null);
    const [validDropTargets, setValidDropTargets] = useState<Set<TaskStatus>>(new Set());

    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    );

    const handleDragStart = useCallback(
        (e: DragStartEvent) => {
            const task = tasks.find((item) => item.id === e.active.id);
            setActiveTask(task ?? null);
            if (task) {
                setValidDropTargets(new Set(ALLOWED_TASK_TRANSITIONS[task.status as TaskStatus]));
            }
        },
        [tasks],
    );

    const handleDragOver = useCallback(
        (e: DragOverEvent) => {
            const { active, over } = e;
            if (!over) return;

            const taskId = active.id as string;
            const targetStatus = over.id as string;

            if (!COLUMN_ORDER.includes(targetStatus as TaskStatus)) return;

            const source = dragState ?? grouped;
            const task = tasks.find((item) => item.id === taskId);
            if (!task) return;

            const fromStatus = COLUMN_ORDER.find((status) =>
                source[status].some((item) => item.id === taskId),
            );
            if (!fromStatus) return;

            const toStatus = targetStatus as TaskStatus;
            if (fromStatus === toStatus) return;

            // 2.9: Validate transition before optimistic update
            if (!isAllowedTaskTransition(fromStatus, toStatus)) return;

            const updatedFrom = source[fromStatus].filter(
                (item) => item.id !== taskId,
            );
            const updatedTo = [
                ...source[toStatus].filter((item) => item.id !== taskId),
                { ...task, status: toStatus },
            ];

            setDragState({
                ...source,
                [fromStatus]: updatedFrom,
                [toStatus]: updatedTo,
            });
        },
        [dragState, grouped, tasks],
    );

    const handleDragEnd = useCallback(
        async (e: DragEndEvent) => {
            setActiveTask(null);
            setDragState(null);
            setValidDropTargets(new Set());

            const { active, over } = e;
            if (!over) return;

            const taskId = active.id as string;
            const targetStatus = over.id as string;
            const task = tasks.find((item) => item.id === taskId);

            if (!task || task.status === targetStatus) return;
            if (!COLUMN_ORDER.includes(targetStatus as TaskStatus)) return;
            if (
                !isAllowedTaskTransition(
                    task.status as TaskStatus,
                    targetStatus as TaskStatus,
                )
            ) {
                toast.error(
                    `Cannot move ${STATUS_LABELS[task.status as TaskStatus]} directly to ${STATUS_LABELS[targetStatus as TaskStatus]}`,
                );
                return;
            }

            try {
                await apiClient.transitionTaskStatus(
                    taskId,
                    targetStatus as TaskStatus,
                );
                fetchTasks();
                toast.success(
                    `Moved to ${STATUS_LABELS[targetStatus as TaskStatus]}`,
                );
            } catch (error) {
                toast.error(
                    error instanceof Error
                        ? error.message
                        : "Failed to move task",
                );
                fetchTasks();
            }
        },
        [fetchTasks, tasks],
    );

    const handleDragCancel = useCallback((_e: DragCancelEvent) => {
        setActiveTask(null);
        setDragState(null);
        setValidDropTargets(new Set());
    }, []);

    return {
        activeTask,
        liveTasksByStatus: dragState ?? grouped,
        sensors,
        collisionDetection: pointerWithin,
        handleDragStart,
        handleDragOver,
        handleDragEnd,
        handleDragCancel,
        validDropTargets,
        isDragActive: activeTask !== null,
    };
}
