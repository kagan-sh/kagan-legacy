import { useCallback, useEffect, useState } from "react";
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
import { apiClient } from "@/lib/api/client";
import type { WireChatSession, WireChatSessionSummary } from "@/lib/api/types";
import { ChatView } from "@/components/chat/chat-view";
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
import { useChatStream } from "@/lib/chat/use-chat-stream";

const INITIAL_VISIBLE = 30;

function toSessionSummary(session: WireChatSession): WireChatSessionSummary {
    return {
        id: session.id,
        label: session.label,
        source: session.source,
        agent_backend: session.agent_backend ?? null,
        project_id: session.project_id ?? null,
        updated_at: session.updated_at,
        message_count: session.message_count,
    };
}

interface OrchestratorChatPanelProps {
    sessionId: string;
    layout: Exclude<RightRailMode, "none">;
    onSetLayout: (layout: Exclude<RightRailMode, "none">) => void;
    onClose: () => void;
    surface?: "rail" | "workspace";
    onSessionUpdated?: (session: WireChatSessionSummary) => void;
}

export function OrchestratorChatPanel({
    sessionId,
    layout,
    onSetLayout,
    onClose,
    surface = "rail",
    onSessionUpdated,
}: OrchestratorChatPanelProps) {
    const isMobile = useIsMobile();
    const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);

    const {
        messages,
        streamEntries,
        isStreaming,
        loading,
        label,
        agentBackend,
        availableBackends,
        editPrefill,
        scrollRef,
        handleSend,
        handleInterrupt,
        handleSlashCommand,
        switchBackend,
        setEditPrefill,
        setLabel,
    } = useChatStream(sessionId);

    // Progressive message rendering
    const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE);

    // Notify parent when session metadata updates
    useEffect(() => {
        if (!sessionId || !onSessionUpdated) return;
        apiClient.getChatSession(sessionId).then((session) => {
            onSessionUpdated(toSessionSummary(session));
            setLabel(session.label || "Orchestrator Chat");
        }).catch(() => {});
    // Only run on mount and sessionId change; label/messages are managed by hook
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sessionId]);

    // Fetch active project context for the header
    const [projectContext, setProjectContext] = useState<string | null>(null);
    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const projects = await apiClient.getProjects();
                const active = projects.find((p) => p.active);
                if (cancelled || !active) return;
                const repos = await apiClient.getProjectRepos(active.id);
                const selected = repos.find((r) => r.selected) ?? repos[0];
                const ctx = selected ? `${active.name} / ${selected.name}` : active.name;
                if (!cancelled) setProjectContext(ctx);
            } catch {
                // best-effort
            }
        })();
        return () => { cancelled = true; };
    }, [sessionId]);

    const onSlashCommand = useCallback(
        (command: string) => {
            handleSlashCommand(command, { onNew: () => setSessionPickerOpen(true) });
        },
        [handleSlashCommand, setSessionPickerOpen],
    );

    const headerSlot = (
        <>
            <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--foreground)]">{label}</p>
                <p className="truncate text-xs text-[var(--muted-foreground)]">
                    Orchestrator
                    {projectContext && (
                        <span className="ml-1.5 text-[var(--primary)]">· {projectContext}</span>
                    )}
                </p>
                {availableBackends.length > 0 && (
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <button
                                type="button"
                                className="mt-0.5 inline-flex items-center gap-1 rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--primary)]"
                            >
                                {agentBackend ?? "default"}
                                <ChevronDown className="size-3" />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                            {availableBackends.map((b) => (
                                <DropdownMenuItem key={b} onSelect={() => void switchBackend(b)}>
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
                {surface === "rail" ? (
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 px-2 text-xs"
                        onClick={() => setSessionPickerOpen(true)}
                    >
                        <PanelsTopLeft className="size-3.5" />
                        Sessions
                    </Button>
                ) : null}
                {surface === "rail" && !isMobile ? (
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
                            <DropdownMenuItem onSelect={() => onSetLayout("chat-right")}>
                                <PanelRight className="size-4" />
                                Dock right
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => onSetLayout("chat-bottom")}>
                                <PanelBottom className="size-4" />
                                Dock bottom
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => onSetLayout("chat-fullscreen")}>
                                <Maximize2 className="size-4" />
                                Fullscreen
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                ) : null}
                {surface === "rail" ? (
                    <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={onClose}
                        aria-label="Close chat panel"
                    >
                        <X className="size-4" />
                    </Button>
                ) : null}
            </div>
        </>
    );

    const footerHint = !isMobile && surface === "rail"
        ? `⌘⇧K sessions · ⌘I toggle${isStreaming ? " · esc stop & edit last" : ""}`
        : undefined;

    return (
        <aside
            data-chat-layout={layout}
            className={cn(
                "flex h-full min-h-0 flex-col bg-[color:var(--surface-0)]",
                surface === "rail" && layout === "chat-right" && "border-l border-[color:var(--border-subtle)]",
                surface === "rail" && layout === "chat-bottom" && "border-t border-[color:var(--border-subtle)]",
                layout === "chat-fullscreen" && "w-full overflow-hidden border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/95 shadow-[var(--ambient-shadow)]",
            )}
        >
            {loading ? (
                <div className="flex h-full items-center justify-center px-4 py-4">
                    <div className="h-12 w-full animate-pulse bg-[var(--muted)]" />
                </div>
            ) : (
                <ChatView
                    sessionId={sessionId}
                    messages={messages}
                    streamEntries={streamEntries}
                    isStreaming={isStreaming}
                    loading={false}
                    editPrefill={editPrefill ?? undefined}
                    onPrefillConsumed={() => setEditPrefill(null)}
                    onSend={handleSend}
                    onInterrupt={handleInterrupt}
                    onSlashCommand={onSlashCommand}
                    scrollRef={scrollRef}
                    visibleCount={visibleCount}
                    onLoadMore={() => setVisibleCount((c) => c + 30)}
                    headerSlot={headerSlot}
                    emptySlot={<ChatOverlayEmptyState />}
                    footerHint={footerHint}
                />
            )}
        </aside>
    );
}
