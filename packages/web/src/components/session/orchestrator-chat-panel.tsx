import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSetAtom } from "jotai";
import {
    ChevronDown,
    Maximize2,
    MoreVertical,
    PanelBottom,
    PanelRight,
    PanelsTopLeft,
    X,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api/client";
import { streamSSE } from "@/lib/api/sse";
import type { WireChatMessage } from "@/lib/api/types";
import {
    ChatInputBar,
    type Attachment,
} from "@/components/chat/chat-input-bar";
import { ChatMessage } from "@/components/chat/chat-message";
import { ChatStreamEntries } from "@/components/chat/chat-stream-entries";
import { ChatOverlayEmptyState } from "@/components/session/chat-overlay-empty-state";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { sessionPickerOpenAtom, type RightRailMode } from "@/lib/atoms/ui";
import { useIsMobile } from "@/lib/hooks/use-mobile";
import { cn } from "@/lib/utils";

type StreamEntry =
    | { kind: "text"; content: string }
    | { kind: "thought"; content: string }
    | {
          kind: "tool";
          id: string;
          name: string;
          status: "running" | "done";
          detail?: string;
      }
    | { kind: "note"; message: string }
    | { kind: "error"; message: string };

interface OrchestratorChatPanelProps {
    sessionId: string;
    layout: Exclude<RightRailMode, "none">;
    onSetLayout: (layout: Exclude<RightRailMode, "none">) => void;
    onClose: () => void;
}

export function OrchestratorChatPanel({
    sessionId,
    layout,
    onSetLayout,
    onClose,
}: OrchestratorChatPanelProps) {
    const isMobile = useIsMobile();
    const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
    const [messages, setMessages] = useState<WireChatMessage[]>([]);
    const [streamEntries, setStreamEntries] = useState<StreamEntry[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [loading, setLoading] = useState(true);
    const [label, setLabel] = useState("Orchestrator Chat");
    const scrollRef = useRef<HTMLDivElement>(null);
    const [projectContext, setProjectContext] = useState<string | null>(null);
    const [agentBackend, setAgentBackend] = useState<string | null>(null);
    const [availableBackends, setAvailableBackends] = useState<string[]>([]);

    // Poll for turn completion after reconnect (e.g. page reload)
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollForTurnCompletion = useCallback(
        (sid: string) => {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = setInterval(async () => {
                try {
                    const status = await apiClient.getTurnStatus(sid);
                    if (!status.active) {
                        if (pollRef.current) clearInterval(pollRef.current);
                        pollRef.current = null;
                        const session = await apiClient.getChatSession(sid);
                        setMessages(session.messages);
                        setStreamEntries([]);
                        setIsStreaming(false);
                    }
                } catch {
                    if (pollRef.current) clearInterval(pollRef.current);
                    pollRef.current = null;
                    setIsStreaming(false);
                }
            }, 2000);
        },
        [],
    );

    useEffect(() => {
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, []);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        setMessages([]);
        setStreamEntries([]);
        setIsStreaming(false);

        apiClient
            .getChatSession(sessionId)
            .then(async (session) => {
                if (cancelled) return;
                setMessages(session.messages);
                setLabel(session.label || "Orchestrator Chat");
                setAgentBackend(session.agent_backend ?? null);

                // Check if a turn is still running (e.g. after page reload)
                const turnStatus = await apiClient.getTurnStatus(sessionId);
                if (!cancelled && turnStatus.active) {
                    setIsStreaming(true);
                    setStreamEntries([
                        {
                            kind: "note",
                            message:
                                "Agent is working\u2026 (reconnected)",
                        },
                    ]);
                    pollForTurnCompletion(sessionId);
                }
            })
            .catch((error) => {
                if (!cancelled) {
                    toast.error(
                        error instanceof Error
                            ? error.message
                            : "Session not found",
                    );
                }
            })
            .finally(() => {
                if (!cancelled) {
                    setLoading(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, [sessionId, pollForTurnCompletion]);

    // Fetch active project/repo for context indicator
    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const projects = await apiClient.getProjects();
                const active = projects.find((p) => p.active);
                if (cancelled || !active) return;
                const repos = await apiClient.getProjectRepos(active.id);
                const selected = repos.find((r) => r.selected) ?? repos[0];
                const ctx = selected
                    ? `${active.name} / ${selected.name}`
                    : active.name;
                setProjectContext(ctx);
            } catch {
                // Best-effort
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [sessionId]); // Re-fetch when session changes

    // Fetch available backends
    useEffect(() => {
        apiClient
            .getChatAgents()
            .then((resp) => setAvailableBackends(resp.backends))
            .catch(() => {});
    }, []);

    const switchBackend = useCallback(
        async (backend: string) => {
            try {
                await apiClient.updateChatSession(sessionId, {
                    agent_backend: backend,
                });
                setAgentBackend(backend);
                toast.success(`Switched to ${backend}`);
            } catch (error) {
                toast.error(
                    error instanceof Error
                        ? error.message
                        : "Failed to switch backend",
                );
            }
        },
        [sessionId],
    );

    // Abort controller ref for SSE chat stream
    const chatAbortRef = useRef<AbortController | null>(null);

    // Helper: process a single SSE chunk from the chat stream
    const handleChatSSEMessage = useCallback(
        (data: Record<string, unknown>) => {
            const t = data.t as string;
            if (t === "CHAT_CHUNK") {
                setIsStreaming(true);
                const content = (data.content as string) ?? "";
                const thought = Boolean(data.thought);
                if (!content) return;
                setStreamEntries((prev) => {
                    const kind = thought ? "thought" : "text";
                    const last = prev.at(-1);
                    if (last && last.kind === kind) {
                        const next = [...prev];
                        next[next.length - 1] = {
                            ...last,
                            content: last.content + content,
                        };
                        return next;
                    }
                    return [...prev, { kind, content }];
                });
            } else if (t === "CHAT_TOOL_START") {
                setIsStreaming(true);
                const tool = (data.tool as string) ?? "tool";
                setStreamEntries((prev) => [
                    ...prev,
                    {
                        kind: "tool",
                        id: `tool-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                        name: tool,
                        status: "running",
                    },
                ]);
            } else if (t === "CHAT_TOOL_PROGRESS") {
                const tool = (data.tool as string) ?? "tool";
                const status = (data.status as string) ?? undefined;
                setStreamEntries((prev) => {
                    const next = [...prev];
                    for (let i = next.length - 1; i >= 0; i--) {
                        const entry = next[i];
                        if (entry?.kind === "tool" && entry.name === tool) {
                            next[i] = {
                                ...entry,
                                status:
                                    status === "done" ? "done" : entry.status,
                                detail: status ?? entry.detail,
                            };
                            break;
                        }
                    }
                    return next;
                });
            } else if (t === "CHAT_ERROR") {
                setStreamEntries((prev) => [
                    ...prev,
                    {
                        kind: "error",
                        message:
                            (data.error as string) ?? "An error occurred",
                    },
                ]);
                setIsStreaming(false);
            } else if (t === "CHAT_DONE") {
                setStreamEntries([]);
                setIsStreaming(false);
                apiClient
                    .getChatSession(sessionId)
                    .then((session) => setMessages(session.messages))
                    .catch(() => {});
            } else if (t === "CHAT_SESSION_UPDATED") {
                if (typeof data.label === "string") {
                    setLabel(data.label);
                }
            }
        },
        [sessionId],
    );

    useEffect(() => {
        scrollRef.current?.scrollTo({
            top: scrollRef.current.scrollHeight,
            behavior: "smooth",
        });
    }, [messages, streamEntries]);

    const handleSend = useCallback(
        (text: string, attachments?: Attachment[]) => {
            setIsStreaming(true);

            const displayText = attachments?.length
                ? `${text}\n\n[Attachments: ${attachments.map((attachment) => attachment.name).join(", ")}]`
                : text;
            setMessages((prev) => [
                ...prev,
                { role: "user", content: displayText },
            ]);

            const wireAttachments = attachments
                ?.filter((attachment) => attachment.content)
                .map((attachment) => ({
                    type: attachment.type,
                    name: attachment.name,
                    mime_type:
                        attachment.file?.type ??
                        (attachment.type === "image"
                            ? "image/png"
                            : "text/plain"),
                    data: attachment.content!,
                }));

            // Stream the chat turn via SSE POST
            chatAbortRef.current?.abort();
            const controller = new AbortController();
            chatAbortRef.current = controller;

            (async () => {
                try {
                    for await (const chunk of streamSSE<Record<string, unknown>>(
                        `/api/chat/${sessionId}/stream`,
                        {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                text,
                                ...(wireAttachments?.length
                                    ? { attachments: wireAttachments }
                                    : {}),
                            }),
                            signal: controller.signal,
                        },
                    )) {
                        handleChatSSEMessage(chunk);
                    }
                } catch (err) {
                    if (controller.signal.aborted) return;
                    setStreamEntries((prev) => [
                        ...prev,
                        {
                            kind: "error",
                            message:
                                err instanceof Error
                                    ? err.message
                                    : "Stream failed",
                        },
                    ]);
                    setIsStreaming(false);
                }
            })();
        },
        [sessionId, handleChatSSEMessage],
    );

    const handleInterrupt = useCallback(() => {
        if (!isStreaming) return;
        // Abort the SSE stream locally
        chatAbortRef.current?.abort();
        // Tell the server to cancel the turn
        fetch(
            `${apiClient.getBaseUrl()}/api/chat/${sessionId}/interrupt`,
            { method: "POST" },
        ).catch(() => {});
        setStreamEntries((prev) => [
            ...prev,
            { kind: "note", message: "Interrupted by user." },
        ]);
        setIsStreaming(false);
    }, [isStreaming, sessionId]);

    const handleSlashCommand = useCallback(
        (command: string) => {
            const [cmd, ...args] = command.split(" ");
            if (cmd === "/clear") {
                setMessages([]);
                setStreamEntries([]);
                setIsStreaming(false);
                return;
            }
            if (cmd === "/new" || cmd === "/exit") {
                setSessionPickerOpen(true);
                return;
            }
            if (cmd === "/help") {
                setMessages((prev) => [
                    ...prev,
                    {
                        role: "assistant",
                        content:
                            "Available commands: /clear, /new, /flow <goal>, /agents <name>, /exit, /help",
                    },
                ]);
                return;
            }
            if (cmd === "/agents") {
                if (args.length > 0) {
                    void switchBackend(args.join(" "));
                } else {
                    setMessages((prev) => [
                        ...prev,
                        {
                            role: "assistant",
                            content:
                                "Use `/agents <name>` to switch the orchestrator backend.",
                        },
                    ]);
                }
                return;
            }
            if (cmd === "/flow") {
                const goal = args.join(" ").trim();
                const lines = [
                    "**Structured flow: Plan → Execute → Orchestrate**",
                    "",
                    goal ? `**Goal:** ${goal}` : "",
                    "1. **PLAN** — State the outcome, constraints, and acceptance criteria in 1–3 bullets.",
                    "2. **EXECUTE** — Implement one small step at a time and verify each step.",
                    "3. **ORCHESTRATE** — Summarize what changed, what was verified, and the next action.",
                    "",
                    '_Tip: Start your next message with "Plan for: <goal>" to begin explicitly._',
                ].filter(Boolean);
                setMessages((prev) => [
                    ...prev,
                    { role: "user", content: command },
                    { role: "assistant", content: lines.join("\n") },
                ]);
                return;
            }
            handleSend(command);
        },
        [handleSend, setSessionPickerOpen, switchBackend],
    );

    // Progressive rendering: show only the last 30 messages initially
    const INITIAL_VISIBLE = 30;
    const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE);
    const visibleMessages = useMemo(
        () => messages.slice(Math.max(0, messages.length - visibleCount)),
        [messages, visibleCount],
    );
    const hasEarlierMessages = messages.length > visibleCount;

    const hasContent =
        messages.length > 0 || streamEntries.length > 0 || isStreaming;

    return (
        <aside
            data-chat-layout={layout}
            className={cn(
                "flex h-full min-h-0 flex-col bg-[color:var(--surface-0)]",
                layout === "chat-right" &&
                    "border-l border-[color:var(--border-subtle)]",
                layout === "chat-bottom" &&
                    "border-t border-[color:var(--border-subtle)]",
                layout === "chat-fullscreen" &&
                    "w-full overflow-hidden border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/95 shadow-[var(--ambient-shadow)]",
            )}
        >
            <div className="flex items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
                <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--foreground)]">
                        {label}
                    </p>
                    <p className="truncate text-xs text-[var(--muted-foreground)]">
                        Orchestrator
                        {projectContext && (
                            <span className="ml-1.5 text-[var(--primary)]">
                                · {projectContext}
                            </span>
                        )}
                    </p>
                    {availableBackends.length > 0 && (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <button
                                    type="button"
                                    className="mt-0.5 inline-flex items-center gap-1 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
                                >
                                    {agentBackend ?? "default"}
                                    <ChevronDown className="size-3" />
                                </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="start">
                                {availableBackends.map((b) => (
                                    <DropdownMenuItem
                                        key={b}
                                        onSelect={() =>
                                            void switchBackend(b)
                                        }
                                    >
                                        {b}
                                        {b === agentBackend && (
                                            <span className="ml-auto text-[10px] text-[var(--muted-foreground)]">
                                                active
                                            </span>
                                        )}
                                    </DropdownMenuItem>
                                ))}
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}
                </div>
                <div className="flex items-center gap-1">
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 px-2 text-xs"
                        onClick={() => setSessionPickerOpen(true)}
                    >
                        <PanelsTopLeft className="size-3.5" />
                        Sessions
                    </Button>
                    {!isMobile && (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    aria-label="Chat layout options"
                                >
                                    <MoreVertical className="size-4" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                <DropdownMenuItem
                                    onSelect={() => onSetLayout("chat-right")}
                                >
                                    <PanelRight className="size-4" />
                                    Dock right
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                    onSelect={() => onSetLayout("chat-bottom")}
                                >
                                    <PanelBottom className="size-4" />
                                    Dock bottom
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                    onSelect={() =>
                                        onSetLayout("chat-fullscreen")
                                    }
                                >
                                    <Maximize2 className="size-4" />
                                    Fullscreen
                                </DropdownMenuItem>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}
                    <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={onClose}
                        aria-label="Close chat panel"
                    >
                        <X className="size-4" />
                    </Button>
                </div>
            </div>

            <div
                ref={scrollRef}
                className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
            >
                {loading ? (
                    <div className="h-12 w-full animate-pulse bg-[var(--muted)]" />
                ) : !hasContent ? (
                    <ChatOverlayEmptyState />
                ) : (
                    <div className="divide-y divide-[color:var(--border-subtle)]">
                        {hasEarlierMessages && (
                            <button
                                type="button"
                                onClick={() => setVisibleCount((c) => c + 30)}
                                className="mb-3 flex w-full items-center justify-center gap-2 border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-3 py-2 font-code text-xs text-[var(--muted-foreground)] transition-colors hover:bg-[color:var(--muted)] hover:text-[var(--foreground)]"
                            >
                                Load earlier messages
                            </button>
                        )}
                        {visibleMessages.map((message, index) => (
                            <ChatMessage
                                key={`rail-${sessionId}-${messages.length - visibleMessages.length + index}-${message.role}-${message.content.slice(0, 24)}`}
                                message={message}
                            />
                        ))}
                        {streamEntries.length > 0 ? (
                            <div className="pt-0">
                                <ChatStreamEntries entries={streamEntries} />
                            </div>
                        ) : null}
                    </div>
                )}
            </div>

            {!isMobile && (
                <div className="border-t border-[color:var(--border-subtle)] px-4 py-1.5 text-center font-code text-[10px] tracking-[0.12em] text-[var(--muted-foreground)]">
                    ⌘⇧K sessions · ⌘I toggle · esc stop
                </div>
            )}

            <ChatInputBar
                onSend={handleSend}
                onSlashCommand={handleSlashCommand}
                onInterrupt={handleInterrupt}
                disableSend={isStreaming}
            />
        </aside>
    );
}
