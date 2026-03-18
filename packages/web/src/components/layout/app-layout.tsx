import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { ActivityBar } from "@/components/layout/activity-bar";
import { CommandPalette } from "@/components/layout/command-palette";
import { HelpOverlay } from "@/components/layout/help-overlay";
import { HeaderBar } from "@/components/layout/header-bar";
import { MobileTabs } from "@/components/layout/mobile-tabs";
import { ResizeHandle } from "@/components/layout/resize-handle";
import { ChatSidePanel } from "@/components/session/chat-side-panel";
import { OrchestratorChatPanel } from "@/components/session/orchestrator-chat-panel";
import { SessionPicker } from "@/components/session/session-picker";
import { PluginImportDialog } from "@/components/board/plugin-import-dialog";
import { ErrorBoundary } from "@/components/shared/error-boundary";
import { useEventStream } from "@/lib/hooks/use-event-stream";
import { useIsMobile } from "@/lib/hooks/use-mobile";
import { apiClient } from "@/lib/api/client";
import {
    fetchTasksAtom,
    projectSwitchVersionAtom,
    tasksAtom,
} from "@/lib/atoms/board";
import {
    commandPaletteOpenAtom,
    helpOverlayOpenAtom,
    pluginImportOpenAtom,
    rightRailChatSessionIdAtom,
    rightRailModeAtom,
    rightRailTaskIdAtom,
    sessionPickerOpenAtom,
} from "@/lib/atoms/ui";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { isEditableTarget, hasOpenOverlay } from "@/lib/utils/dom";

type DockedChatRailMode = "chat-right" | "chat-bottom";

function cycleDockMode(mode: DockedChatRailMode): DockedChatRailMode | "none" {
    if (mode === "chat-right") return "chat-bottom";
    return "none"; // chat-bottom -> close
}

function AppLayout() {
    useEventStream();
    const isMobile = useIsMobile();
    const location = useLocation();
    const navigate = useNavigate();
    const [, setCommandOpen] = useAtom(commandPaletteOpenAtom);
    const setHelpOverlayOpen = useSetAtom(helpOverlayOpenAtom);
    const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
    const [pluginImportOpen, setPluginImportOpen] =
        useAtom(pluginImportOpenAtom);
    const [railMode, setRailMode] = useAtom(rightRailModeAtom);
    const railTaskId = useAtomValue(rightRailTaskIdAtom);
    const railChatSessionId = useAtomValue(rightRailChatSessionIdAtom);
    const setRailTaskId = useSetAtom(rightRailTaskIdAtom);
    const setRailChatSessionId = useSetAtom(rightRailChatSessionIdAtom);
    const projectVersion = useAtomValue(projectSwitchVersionAtom);
    const tasks = useAtomValue(tasksAtom);
    const fetchTasks = useSetAtom(fetchTasksAtom);
    const [projectChecked, setProjectChecked] = useState(false);
    const lastDockModeRef = useRef<DockedChatRailMode>("chat-right");
    const navigateRef = useRef(navigate);
    navigateRef.current = navigate;
    const [railWidth, setRailWidth] = useState(448); // 28rem default
    const [railHeight, setRailHeight] = useState(384); // 24rem default

    const railTaskExecutionMode = useMemo(
        () =>
            railTaskId
                ? tasks.find((t) => t.id === railTaskId)?.execution_mode
                : undefined,
        [railTaskId, tasks],
    );

    const MIN_RAIL = 280;
    const MAX_RAIL_W = 800;
    const MAX_RAIL_H = 600;

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
            .then(async (projects) => {
                if (cancelled) return;
                const active = projects.find((p) => p.active);
                if (active) {
                    await fetchTasks();
                    if (!cancelled) setProjectChecked(true);
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

    const closeChatRail = () => {
        setRailMode("none");
    };

    const openChatRail = (mode: DockedChatRailMode = "chat-right") => {
        const nextTaskId = currentTaskId ?? railTaskId;
        if (!nextTaskId) return;
        setRailTaskId(nextTaskId);
        setRailChatSessionId(null);
        setRailMode(mode);
    };

    const setChatRailLayout = (
        mode: "chat-right" | "chat-bottom" | "chat-fullscreen",
    ) => {
        if (mode === "chat-right" || mode === "chat-bottom") {
            lastDockModeRef.current = mode;
        }
        setRailMode(mode);
    };

    const toggleAIPanel = useCallback(async () => {
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
                const orch = sessions
                    .filter((s) =>
                        ["orchestrator", "web"].includes(
                            s.source.toLowerCase(),
                        ),
                    )
                    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
                const sid =
                    orch.length > 0
                        ? orch[0]!.id
                        : (await apiClient.createChatSession({})).id;
                setRailTaskId(null);
                setRailChatSessionId(sid);
                setRailMode("chat-right");
            } catch {
                setSessionPickerOpen(true);
            }
        }
    }, [
        closeChatRail,
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
    ]);

    useEffect(() => {
        if (railMode === "chat-right" || railMode === "chat-bottom") {
            lastDockModeRef.current = railMode;
        }
    }, [railMode]);

    // Auto-open orchestrator chat rail in vertical split on /board (like TUI)
    const autoOpenedRef = useRef(false);
    useEffect(() => {
        if (autoOpenedRef.current) return;
        if (!projectChecked || isMobile) return;
        if (!location.pathname.startsWith("/board")) return;
        if (railMode !== "none") return;
        autoOpenedRef.current = true;

        void (async () => {
            try {
                const sessions = await apiClient.getChatSessions();
                const orchestratorSessions = sessions
                    .filter((s) =>
                        ["orchestrator", "web"].includes(
                            s.source.toLowerCase(),
                        ),
                    )
                    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
                let sessionId: string;
                if (orchestratorSessions.length > 0) {
                    sessionId = orchestratorSessions[0]!.id;
                } else {
                    const created = await apiClient.createChatSession({});
                    sessionId = created.id;
                }
                setRailTaskId(null);
                setRailChatSessionId(sessionId);
                setRailMode("chat-right");
            } catch {
                // Silently fail — user can open manually
            }
        })();
    }, [
        projectChecked,
        isMobile,
        location.pathname,
        railMode,
        setRailChatSessionId,
        setRailMode,
        setRailTaskId,
    ]);

    // On project switch: auto-attach to latest orchestrator session for new project
    const prevProjectVersionRef = useRef(projectVersion);
    useEffect(() => {
        if (projectVersion === prevProjectVersionRef.current) return;
        prevProjectVersionRef.current = projectVersion;
        if (isMobile) return;

        // Always create a fresh session for the new project context
        void (async () => {
            try {
                const created = await apiClient.createChatSession({});
                setRailTaskId(null);
                setRailChatSessionId(created.id);
                if (railMode === "none") {
                    setRailMode("chat-right");
                }
            } catch {
                // Best-effort — user can manually switch via Session Switcher
            }
        })();
    }, [
        projectVersion,
        isMobile,
        railMode,
        setRailChatSessionId,
        setRailMode,
        setRailTaskId,
    ]);

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            const lowerKey = event.key.toLowerCase();
            const dialogOpen = hasOpenOverlay();
            const railOpen =
                railMode !== "none" && Boolean(railTaskId || railChatSessionId);
            const hasTask = Boolean(currentTaskId ?? railTaskId);

            // Cmd/Ctrl+Shift+P — Quick Actions (canonical)
            if (
                (event.metaKey || event.ctrlKey) &&
                event.shiftKey &&
                lowerKey === "p"
            ) {
                event.preventDefault();
                setCommandOpen((prev) => {
                    const next = !prev;
                    if (next) {
                        setSessionPickerOpen(false);
                        setHelpOverlayOpen(false);
                    }
                    return next;
                });
                return;
            }

            // Cmd/Ctrl+I — AI Panel cycle (right → bottom → close)
            if (
                (event.metaKey || event.ctrlKey) &&
                !event.shiftKey &&
                lowerKey === "i"
            ) {
                event.preventDefault();
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
                    // No task context — open orchestrator chat directly
                    void (async () => {
                        try {
                            const sessions = await apiClient.getChatSessions();
                            const orch = sessions
                                .filter((s) =>
                                    ["orchestrator", "web"].includes(
                                        s.source.toLowerCase(),
                                    ),
                                )
                                .sort((a, b) =>
                                    b.updated_at.localeCompare(a.updated_at),
                                );
                            let sid: string;
                            if (orch.length > 0) {
                                sid = orch[0]!.id;
                            } else {
                                const created =
                                    await apiClient.createChatSession({});
                                sid = created.id;
                            }
                            setRailTaskId(null);
                            setRailChatSessionId(sid);
                            setRailMode("chat-right");
                        } catch {
                            // Fallback: open session picker on error
                            setSessionPickerOpen(true);
                        }
                    })();
                }
                return;
            }

            // Cmd/Ctrl+Shift+F — Toggle AI Panel fullscreen
            if (
                (event.metaKey || event.ctrlKey) &&
                event.shiftKey &&
                lowerKey === "f"
            ) {
                event.preventDefault();
                if (railOpen && railMode === "chat-fullscreen") {
                    setChatRailLayout(lastDockModeRef.current);
                } else if (railOpen) {
                    setChatRailLayout("chat-fullscreen");
                }
                return;
            }

            // Cmd/Ctrl+Shift+K — Session Switcher (canonical)
            if (
                (event.metaKey || event.ctrlKey) &&
                event.shiftKey &&
                lowerKey === "k"
            ) {
                event.preventDefault();
                setSessionPickerOpen((prev) => {
                    const next = !prev;
                    if (next) {
                        setCommandOpen(false);
                        setHelpOverlayOpen(false);
                    }
                    return next;
                });
                return;
            }

            if (
                !isEditableTarget(event.target) &&
                (event.key === "?" || event.key === "F1")
            ) {
                event.preventDefault();
                setCommandOpen(false);
                setSessionPickerOpen(false);
                setHelpOverlayOpen(true);
                return;
            }

            if (isMobile || dialogOpen) return;

            // Esc — close chat rail (interrupt-first: chat-input-bar stops propagation when busy)
            if (event.key === "Escape" && railOpen) {
                event.preventDefault();
                closeChatRail();
                return;
            }
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [
        closeChatRail,
        currentTaskId,
        isMobile,
        openChatRail,
        railChatSessionId,
        railMode,
        railTaskId,
        setCommandOpen,
        setHelpOverlayOpen,
        setChatRailLayout,
        setSessionPickerOpen,
    ]);

    if (!projectChecked) {
        return (
            <div className="flex h-screen items-center justify-center bg-[color:var(--surface-0)]">
                <Spinner className="size-8 text-[var(--muted-foreground)]" />
            </div>
        );
    }

    return (
        <>
            <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-[var(--primary)] focus:px-4 focus:py-2 focus:text-[var(--primary-foreground)]"
            >
                Skip to content
            </a>

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
                                if (railMode === "chat-fullscreen") {
                                    setChatRailLayout(lastDockModeRef.current);
                                } else if (railMode !== "none") {
                                    setChatRailLayout("chat-fullscreen");
                                }
                            }}
                            aiPanelOpen={
                                railMode !== "none" &&
                                Boolean(railTaskId || railChatSessionId)
                            }
                            aiPanelFullscreen={railMode === "chat-fullscreen"}
                        />
                    )}

                    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                        <div className="flex min-h-0 min-w-0 flex-1">
                            <main
                                id="main-content"
                                className={cn(
                                    "min-h-0 min-w-0 flex-1 overflow-y-auto bg-[color:var(--surface-0)] pb-[calc(5rem+env(safe-area-inset-bottom))] lg:pb-0",
                                    railMode === "chat-fullscreen" &&
                                        "overflow-hidden",
                                )}
                            >
                                <Outlet />
                            </main>

                            {!isMobile &&
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
                                                executionMode={
                                                    railTaskExecutionMode
                                                }
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
                                            executionMode={
                                                railTaskExecutionMode
                                            }
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

                {isMobile && <MobileTabs onToggleAIPanel={toggleAIPanel} />}
            </div>

            {isMobile &&
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
                                executionMode={railTaskExecutionMode}
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
                                    executionMode={railTaskExecutionMode}
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

            <CommandPalette />
            <SessionPicker />
            <HelpOverlay />
            <PluginImportDialog
                open={pluginImportOpen}
                onOpenChange={setPluginImportOpen}
            />
        </>
    );
}

export const Component = AppLayout;
