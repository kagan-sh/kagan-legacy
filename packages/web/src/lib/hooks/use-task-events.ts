import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api/client";
import type { WireEvent, WireTask, WireTaskSession } from "@/lib/api/types";
import { kaganWs, type WsInboundMessage } from "@/lib/api/websocket";
import { mergeWireEvents } from "@/lib/utils/events";
import { deriveTaskRunningSince } from "@/lib/utils/task-runtime";
import { useFollowUpQueue } from "@/lib/hooks/use-follow-up-queue";
import { usePageVisible } from "@/lib/hooks/use-page-visible";
import type { UserFollowUp } from "@/components/session/event-stream";
import type { QueuedPrompt } from "@/components/session/follow-up-queue";

interface UseTaskEventsOptions {
    /** Initial event fetch limit. Default 400. */
    initialLimit?: number;
    /** Polling interval in ms. Default 2500. */
    pollInterval?: number;
    /** Filter events to a specific session ID. When changed, events reset and refetch. */
    sessionId?: string | null;
}

interface UseTaskEventsResult {
    task: WireTask | null;
    events: WireEvent[];
    loading: boolean;
    runningSince: string | null;
    isRunning: boolean;
    sessions?: WireTaskSession[];

    // Follow-up queue
    sentFollowUps: UserFollowUp[];
    queue: QueuedPrompt[];
    sendingFollowUp: boolean;
    queuePrompt: (
        text: string,
        attachments?: { name: string; type: string }[],
    ) => void;
    removePrompt: (id: string) => void;
    editPrompt: (id: string, text: string) => void;
    interruptAndSend: (id: string) => void;

    // Load-earlier pagination
    hasMore: boolean;
    loadingMore: boolean;
    loadEarlier: () => void;
}

/** How many events to fetch per "load earlier" batch. */
const LOAD_EARLIER_BATCH = 200;

/**
 * Shared hook for loading task events, subscribing to WS updates,
 * and managing the follow-up prompt queue. Used by both the session
 * page and the chat side panel — single source of truth.
 */
export function useTaskEvents(
    taskId: string | undefined,
    options?: UseTaskEventsOptions,
): UseTaskEventsResult {
    const initialLimit = options?.initialLimit ?? 400;
    const pollInterval = options?.pollInterval ?? 2500;
    const sessionId = options?.sessionId ?? undefined;

    const [task, setTask] = useState<WireTask | null>(null);
    const [events, setEvents] = useState<WireEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [sessions, setSessions] = useState<WireTaskSession[]>([]);
    const [hasMore, setHasMore] = useState(false);
    const [loadingMore, setLoadingMore] = useState(false);
    const eventsRef = useRef(events);
    eventsRef.current = events;
    const latestCursorRef = useRef<{ ts: string; id: string } | null>(null);

    // Compose the follow-up queue hook
    const followUp = useFollowUpQueue(taskId);

    // Track previous sessionId to detect changes and reset
    const prevSessionId = useRef(sessionId);
    useEffect(() => {
        if (prevSessionId.current !== sessionId) {
            prevSessionId.current = sessionId;
            setEvents([]);
            setHasMore(false);
            setLoading(true);
        }
    }, [sessionId]);

    // Initial load
    useEffect(() => {
        if (!taskId) return;
        setLoading(true);
        const sessionsFetch =
            typeof apiClient.getTaskSessions === "function"
                ? apiClient.getTaskSessions(taskId)
                : Promise.resolve([]);
        void Promise.all([
            apiClient.getTask(taskId),
            apiClient.getTaskEvents(taskId, {
                limit: initialLimit,
                tail: true,
                session_id: sessionId,
            }),
            sessionsFetch,
        ])
            .then(([nextTask, nextEvents, nextSessions]) => {
                setTask(nextTask);
                setEvents((prev) => mergeWireEvents(prev, nextEvents));
                setSessions(nextSessions);
                setHasMore(nextEvents.length >= initialLimit);
            })
            .catch((error) => {
                toast.error(
                    error instanceof Error
                        ? error.message
                        : "Failed to load session",
                );
            })
            .finally(() => setLoading(false));
    }, [taskId, initialLimit, sessionId]);

    useEffect(() => {
        const last = events[events.length - 1];
        if (last) {
            latestCursorRef.current = { ts: last.created_at, id: last.id };
            return;
        }
        latestCursorRef.current = null;
    }, [events]);

    // Live WS event stream — only accept events matching our session filter
    useEffect(() => {
        if (!taskId) return;
        return kaganWs.on("SESSION_EVENT", (data: WsInboundMessage) => {
            if (data.task_id !== taskId || !data.event) return;
            const nextEvent = data.event as WireEvent;

            // If filtering by session, only accept matching events
            if (
                sessionId &&
                nextEvent.session_id &&
                nextEvent.session_id !== sessionId
            )
                return;

            setEvents((prev) => mergeWireEvents(prev, [nextEvent]));
            if (nextEvent.type === "TASK_STATUS_CHANGED") {
                const to = nextEvent.payload?.to;
                if (typeof to === "string") {
                    setTask((prev) => (prev ? { ...prev, status: to } : prev));
                }
            }
        });
    }, [taskId, sessionId]);

    // Refetch task on TASK_UPDATED broadcast
    useEffect(() => {
        if (!taskId) return;
        return kaganWs.on("TASK_UPDATED", (data: WsInboundMessage) => {
            if (data.task_id === taskId) {
                void apiClient
                    .getTask(taskId)
                    .then(setTask)
                    .catch(() => undefined);
            }
        });
    }, [taskId]);

    // Polling refresh — with error counting and visibility awareness
    const pollFailCountRef = useRef(0);
    const isVisible = usePageVisible();

    useEffect(() => {
        if (!taskId) return;
        const refresh = () => {
            if (!isVisible) return;

            const cursor = latestCursorRef.current;
            const eventsFetch = cursor
                ? apiClient.getTaskEvents(taskId, {
                      after: cursor.ts,
                      after_id: cursor.id,
                      limit: 220,
                      session_id: sessionId,
                  })
                : apiClient.getTaskEvents(taskId, {
                      limit: 220,
                      tail: true,
                      session_id: sessionId,
                  });

            void Promise.all([apiClient.getTask(taskId), eventsFetch])
                .then(([nextTask, nextEvents]) => {
                    pollFailCountRef.current = 0;
                    if (nextTask) setTask(nextTask as WireTask);
                    if (Array.isArray(nextEvents) && nextEvents.length > 0) {
                        setEvents((prev) => mergeWireEvents(prev, nextEvents));
                    }
                })
                .catch((err) => {
                    pollFailCountRef.current += 1;
                    if (pollFailCountRef.current === 3) {
                        toast.error(
                            err instanceof Error
                                ? `Event polling failed: ${err.message}`
                                : "Event polling failed — server may be unreachable",
                        );
                    }
                });
        };
        const interval = window.setInterval(refresh, pollInterval);
        return () => window.clearInterval(interval);
    }, [taskId, pollInterval, sessionId, isVisible]);

    // Load earlier events (before the oldest currently loaded)
    const loadEarlier = useCallback(() => {
        if (!taskId || loadingMore) return;
        const oldest = eventsRef.current[0];
        if (!oldest?.created_at) return;

        setLoadingMore(true);
        apiClient
            .getTaskEvents(taskId, {
                limit: LOAD_EARLIER_BATCH,
                before: oldest.created_at,
                session_id: sessionId,
            })
            .then((olderEvents) => {
                if (olderEvents.length > 0) {
                    setEvents((prev) => mergeWireEvents(olderEvents, prev));
                }
                setHasMore(olderEvents.length >= LOAD_EARLIER_BATCH);
            })
            .catch(() => undefined)
            .finally(() => setLoadingMore(false));
    }, [taskId, loadingMore, sessionId]);

    // Derived
    const runningSince = useMemo(
        () => (task ? deriveTaskRunningSince(events, task.status) : null),
        [events, task],
    );
    const isRunning = useMemo(() => {
        if (task?.status !== "IN_PROGRESS") return false;
        // If the most recent session-level event signals the agent stopped,
        // treat the task as idle even though its status hasn't transitioned yet.
        for (let i = events.length - 1; i >= 0; i--) {
            const t = events[i]?.type;
            if (t === "AGENT_FAILED" || t === "AGENT_COMPLETED") return false;
            if (
                t === "AGENT_STATUS" ||
                t === "OUTPUT_CHUNK" ||
                t === "TOOL_CALL_START" ||
                t === "TOOL_CALL_UPDATE"
            )
                return true;
        }
        return true;
    }, [task?.status, events]);

    return {
        task,
        events,
        loading,
        runningSince,
        isRunning,
        sessions,
        hasMore,
        loadingMore,
        loadEarlier,
        ...followUp,
    };
}
