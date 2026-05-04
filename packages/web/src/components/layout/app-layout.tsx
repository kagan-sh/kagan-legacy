import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { SkipLink } from "@/components/a11y/skip-link";
import { ActivityBar } from "@/components/layout/activity-bar";
import { HelpOverlay } from "@/components/layout/help-overlay";
import { HeaderBar } from "@/components/layout/header-bar";
import { MobileTabs } from "@/components/layout/mobile-tabs";
import { ResizeHandle } from "@/components/layout/resize-handle";
import { ChatSidePanel } from "@/components/session/chat-side-panel";
import { OrchestratorChatPanel } from "@/components/session/orchestrator-chat-panel";
import { SessionPicker } from "@/components/session/session-picker";
import { IntegrationImportDialog } from "@/components/board/integration-import-dialog";
import { ErrorBoundary } from "@/components/shared/error-boundary";
import { toast } from "sonner";
import { useEventStream } from "@/lib/hooks/use-event-stream";
import { useIsMobile } from "@/lib/hooks/use-mobile";
import { apiClient } from "@/lib/api/client";
import type { WireChatSessionSummary } from "@kagan/shared-api-client";
import {
    fetchTasksAtom,
    projectSwitchVersionAtom,
} from "@/lib/atoms/board";
import {
    commandPaletteOpenAtom,
    clearRightRailDismissalAtom,
    dismissRightRailContextAtom,
    helpOverlayOpenAtom,
    integrationImportOpenAtom,
    rightRailChatSessionIdAtom,
    rightRailModeAtom,
    rightRailTaskIdAtom,
    sessionPickerOpenAtom,
} from "@/lib/atoms/ui";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { type DockedChatRailMode, cycleDockMode } from "@/lib/layout/dock-mode";

function AppLayout() {
    useEventStream();
    const isMobile = useIsMobile();
    const location = useLocation();
    const navigate = useNavigate();
    const setCommandOpen = useSetAtom(commandPaletteOpenAtom);
    const setHelpOverlayOpen = useSetAtom(helpOverlayOpenAtom);
    const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
    const [integrationImportOpen, setIntegrationImportOpen] =
        useAtom(integrationImportOpenAtom);
    const [railMode, setRailMode] = useAtom(rightRailModeAtom);
    const railTaskId = useAtomValue(rightRailTaskIdAtom);
    const railChatSessionId = useAtomValue(rightRailChatSessionIdAtom);
    const setRailTaskId = useSetAtom(rightRailTaskIdAtom);
    const setRailChatSessionId = useSetAtom(rightRailChatSessionIdAtom);
    const dismissRightRailContext = useSetAtom(dismissRightRailContextAtom);
    const clearRightRailDismissal = useSetAtom(clearRightRailDismissalAtom);
    const projectVersion = useAtomValue(projectSwitchVersionAtom);
    const fetchTasks = useSetAtom(fetchTasksAtom);
    const [projectChecked, setProjectChecked] = useState(false);
    const lastDockModeRef = useRef<DockedChatRailMode>("chat-right");
    const navigateRef = useRef(navigate);
    navigateRef.current = navigate;
    const [railWidth, setRailWidth] = useState(448); // 28rem default
    const [railHeight, setRailHeight] = useState(384); // 24rem default

    const MIN_RAIL = 280;
    const MAX_RAIL_W = 800;
    const MAX_RAIL_H = 600;

    const createOrGetSession = useCallback(
        async (sessions: WireChatSessionSummary[]): Promise<string | null> => {
            try {
                const orchestratorSessions = sessions
                    .filter((s) =>
                        ['orchestrator', 'web'].includes(s.source.toLowerCase()),
                    )
                    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

                const sessionId =
                    orchestratorSessions.length > 0
                        ? orchestratorSessions[0]!.id
                        : (await apiClient.createChatSession({})).id;

                return sessionId;
            } catch (error) {
                const message =
                    error instanceof Error ? error.message : 'Failed to create session';
                toast.error(message);
                return null;
            }
        },
        [],
    );

    // Reset project check when project switches (e.g. from welcome page)
    const prevProjectVersionRef2 = useRef(projectVersion);
    useEffect(() => {
        if (projectVersion !== prevProjectVersionRef2.current) {
            prevProjectVersionRef2.current = projectVersion;
            setProjectChecked(false);
        }
    }, [projectVersion]);

    // Verify active project before rendering the board.  Eagerly fetch tasks
    // so data is ready when the board mounts — avoids a blank-screen flash.
    // navigate is accessed via ref to avoid effect re-runs from unstable
    // useNavigate() references caused by WebSocket-driven re-renders.
    useEffect(() => {
        if (projectChecked) return;
        let cancelled = false;
        apiClient
            .getProjects()
            .then((projects) => {
                if (cancelled) return;
                const active = projects.find((p) => p.active);
                if (active) {
                    // Render the board immediately — don't block on task fetch.
                    // fetchTasks runs in parallel; the board shows a loading
                    // state until tasks arrive via SSE or the fetch resolves.
                    setProjectChecked(true);
                    fetchTasks();
                } else {
                    navigateRef.current("/welcome", { replace: true });
                }
            })
            .catch(() => {
                if (!cancelled)
                    navigateRef.current("/welcome", { replace: true });
            });
        return () => {
            cancelled = true;
        };
    }, [projectChecked, fetchTasks]);

    const currentTaskId = useMemo(() => {
        const taskMatch = /^\/task\/([^/?]+)/.exec(location.pathname);
        if (taskMatch) return taskMatch[1];
        const sessionMatch = /^\/session\/([^/?]+)/.exec(location.pathname);
        if (sessionMatch) return sessionMatch[1];
        return null;
    }, [location.pathname]);
    const workspaceRoute = location.pathname.startsWith("/workspace");

    const closeChatRail = useCallback(() => {
        dismissRightRailContext();
        setRailMode("none");
    }, [dismissRightRailContext, setRailMode]);

    const openChatRail = useCallback((mode: DockedChatRailMode = "chat-right") => {
        const nextTaskId = currentTaskId ?? railTaskId;
        if (!nextTaskId) return;
        clearRightRailDismissal({ kind: "task", id: nextTaskId });
        setRailTaskId(nextTaskId);
        setRailChatSessionId(null);
        setRailMode(mode);
    }, [
        clearRightRailDismissal,
        currentTaskId,
        railTaskId,
        setRailChatSessionId,
        setRailMode,
        setRailTaskId,
    ]);

    const setChatRailLayout = useCallback((
        mode: "chat-right" | "chat-bottom" | "chat-fullscreen",
    ) => {
        if (mode === "chat-right" || mode === "chat-bottom") {
            lastDockModeRef.current = mode;
        }
        setRailMode(mode);
    }, [setRailMode]);

    const toggleAIPanel = useCallback(async () => {
        if (workspaceRoute) return;
        const railOpen =
            railMode !== "none" && Boolean(railTaskId || railChatSessionId);
        const hasTask = Boolean(currentTaskId ?? railTaskId);
        if (
            railOpen &&
            (railMode === "chat-right" || railMode === "chat-bottom")
        ) {
            const next = cycleDockMode(railMode);
            if (next === "none") {
                closeChatRail();
            } else {
                setChatRailLayout(next);
            }
        } else if (railOpen) {
            closeChatRail();
        } else if (hasTask) {
            openChatRail("chat-right");
        } else {
            try {
                const sessions = await apiClient.getChatSessions();
                const sessionId = await createOrGetSession(sessions);
                if (sessionId) {
                    clearRightRailDismissal({ kind: "session", id: sessionId });
                    setRailTaskId(null);
                    setRailChatSessionId(sessionId);
                    setRailMode("chat-right");
                }
            } catch {
                setSessionPickerOpen(true);
            }
        }
    }, [
        closeChatRail,
        createOrGetSession,
        clearRightRailDismissal,
        currentTaskId,
        openChatRail,
        railChatSessionId,
        railMode,
        railTaskId,
        setChatRailLayout,
        setRailChatSessionId,
        setRailMode,
        setRailTaskId,
        setSessionPickerOpen,
        workspaceRoute,
    ]);

    useEffect(() => {
        if (railMode === "chat-right" || railMode === "chat-bottom") {
            lastDockModeRef.current = railMode;
        }
    }, [railMode]);

    // On project switch: auto-attach to latest orchestrator session for new project
    const prevProjectVersionRef = useRef(projectVersion);
    useEffect(() => {
        if (projectVersion === prevProjectVersionRef.current) return;
        prevProjectVersionRef.current = projectVersion;
        if (isMobile) return;

        // Always create a fresh session for the new project context
        void (async () => {
            try {
                const sessionId = await createOrGetSession([]);
                if (sessionId) {
                    setRailTaskId(null);
                    setRailChatSessionId(sessionId);
                    if (railMode === "none") {
                        setRailMode("chat-right");
                    }
                }
            } catch {
                // Best-effort — user can manually switch via Session Switcher
            }
        })();
    }, [
        projectVersion,
        isMobile,
        createOrGetSession,
        railMode,
        setRailChatSessionId,
        setRailMode,
        setRailTaskId,
    ]);

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            const railOpen =
                railMode !== "none" && Boolean(railTaskId || railChatSessionId);

            // Esc — close chat rail (interrupt-first: chat-input-bar stops propagation when busy)
            if (event.key === "Escape" && railOpen) {
                event.preventDefault();
                closeChatRail();
            }
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [closeChatRail, railChatSessionId, railMode, railTaskId]);

    if (!projectChecked) {
        return (
            <div className="flex h-screen items-center justify-center bg-[color:var(--surface-0)]">
                <Spinner className="size-8 text-[var(--muted-foreground)]" />
            </div>
        );
    }

    return (
        <>
            <SkipLink>Skip to content</SkipLink>

            <div className="flex h-screen overflow-hidden bg-[color:var(--surface-0)]">
                {!isMobile && <ActivityBar />}

                <div className="relative flex min-w-0 flex-1 flex-col">
                    {!isMobile && (
                        <HeaderBar
                            onOpenCommandPalette={() => {
                                setSessionPickerOpen(false);
                                setHelpOverlayOpen(false);
                                setCommandOpen(true);
                            }}
                            onOpenHelp={() => {
                                setCommandOpen(false);
                                setSessionPickerOpen(false);
                                setHelpOverlayOpen(true);
                            }}
                            onToggleAIPanel={toggleAIPanel}
                            onToggleFullscreen={() => {
                                if (workspaceRoute) return;
                                if (railMode === "chat-fullscreen") {
                                    setChatRailLayout(lastDockModeRef.current);
                                } else if (railMode !== "none") {
                                    setChatRailLayout("chat-fullscreen");
                                }
                            }}
                            aiPanelAvailable={!workspaceRoute}
                            aiPanelOpen={
                                !workspaceRoute &&
                                railMode !== "none" &&
                                Boolean(railTaskId || railChatSessionId)
                            }
                            aiPanelFullscreen={
                                !workspaceRoute &&
                                railMode === "chat-fullscreen"
                            }
                        />
                    )}

                    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                        <div className="flex min-h-0 min-w-0 flex-1">
                            <main
                                id="main-content"
                                className={cn(
                                    "min-h-0 min-w-0 flex-1 overflow-y-auto bg-[color:var(--surface-0)] pb-[calc(5rem+env(safe-area-inset-bottom))] lg:pb-0",
                                    !workspaceRoute &&
                                        railMode === "chat-fullscreen" &&
                                        "overflow-hidden",
                                )}
                            >
                                <Outlet />
                            </main>

                            {!isMobile &&
                            !workspaceRoute &&
                            railMode === "chat-right" &&
                            (railTaskId || railChatSessionId) ? (
                                <div
                                    className="relative hidden shrink-0 lg:block"
                                    style={{ width: railWidth }}
                                >
                                    <ResizeHandle
                                        edge="left"
                                        onResize={(d) =>
                                            setRailWidth((w) =>
                                                Math.min(
                                                    MAX_RAIL_W,
                                                    Math.max(MIN_RAIL, w + d),
                                                ),
                                            )
                                        }
                                    />
                                    {railTaskId ? (
                                        <ErrorBoundary level="widget">
                                            <ChatSidePanel
                                                taskId={railTaskId}
                                                layout="chat-right"
                                                onSetLayout={setChatRailLayout}
                                                onClose={closeChatRail}
                                            />
                                        </ErrorBoundary>
                                    ) : railChatSessionId ? (
                                        <ErrorBoundary level="widget">
                                            <OrchestratorChatPanel
                                                sessionId={railChatSessionId}
                                                layout="chat-right"
                                                onSetLayout={setChatRailLayout}
                                                onClose={closeChatRail}
                                            />
                                        </ErrorBoundary>
                                    ) : null}
                                </div>
                            ) : null}
                        </div>

                        {!isMobile &&
                        !workspaceRoute &&
                        railMode === "chat-bottom" &&
                        (railTaskId || railChatSessionId) ? (
                            <div
                                className="relative hidden shrink-0 lg:block"
                                style={{ height: railHeight }}
                            >
                                <ResizeHandle
                                    edge="top"
                                    onResize={(d) =>
                                        setRailHeight((h) =>
                                            Math.min(
                                                MAX_RAIL_H,
                                                Math.max(MIN_RAIL, h + d),
                                            ),
                                        )
                                    }
                                />
                                {railTaskId ? (
                                    <ErrorBoundary level="widget">
                                        <ChatSidePanel
                                            taskId={railTaskId}
                                            layout="chat-bottom"
                                            onSetLayout={setChatRailLayout}
                                            onClose={closeChatRail}
                                        />
                                    </ErrorBoundary>
                                ) : railChatSessionId ? (
                                    <ErrorBoundary level="widget">
                                        <OrchestratorChatPanel
                                            sessionId={railChatSessionId}
                                            layout="chat-bottom"
                                            onSetLayout={setChatRailLayout}
                                            onClose={closeChatRail}
                                        />
                                    </ErrorBoundary>
                                ) : null}
                            </div>
                        ) : null}
                    </div>
                </div>

                {isMobile && <MobileTabs />}
            </div>

            {isMobile &&
            !workspaceRoute &&
            railMode !== "none" &&
            (railTaskId || railChatSessionId) ? (
                <div className="fixed inset-0 z-50 flex flex-col bg-[color:var(--surface-0)]">
                    {railTaskId ? (
                        <ErrorBoundary level="widget">
                            <ChatSidePanel
                                taskId={railTaskId}
                                layout="chat-fullscreen"
                                onSetLayout={setChatRailLayout}
                                onClose={closeChatRail}
                            />
                        </ErrorBoundary>
                    ) : railChatSessionId ? (
                        <ErrorBoundary level="widget">
                            <OrchestratorChatPanel
                                sessionId={railChatSessionId}
                                layout="chat-fullscreen"
                                onSetLayout={setChatRailLayout}
                                onClose={closeChatRail}
                            />
                        </ErrorBoundary>
                    ) : null}
                </div>
            ) : null}

            {!isMobile &&
            !workspaceRoute &&
            railMode === "chat-fullscreen" &&
            (railTaskId || railChatSessionId) ? (
                <div className="glass-surface pointer-events-none fixed inset-0 z-40 hidden p-4 lg:block">
                    <div className="pointer-events-auto flex h-full w-full overflow-hidden">
                        {railTaskId ? (
                            <ErrorBoundary level="widget">
                                <ChatSidePanel
                                    taskId={railTaskId}
                                    layout="chat-fullscreen"
                                    onSetLayout={setChatRailLayout}
                                    onClose={closeChatRail}
                                />
                            </ErrorBoundary>
                        ) : railChatSessionId ? (
                            <ErrorBoundary level="widget">
                                <OrchestratorChatPanel
                                    sessionId={railChatSessionId}
                                    layout="chat-fullscreen"
                                    onSetLayout={setChatRailLayout}
                                    onClose={closeChatRail}
                                />
                            </ErrorBoundary>
                        ) : null}
                    </div>
                </div>
            ) : null}

            <SessionPicker />
            <HelpOverlay />
            <IntegrationImportDialog
                open={integrationImportOpen}
                onOpenChange={setIntegrationImportOpen}
            />
        </>
    );
}

export const Component = AppLayout;
