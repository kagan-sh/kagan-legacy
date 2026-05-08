import { useCallback, useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { SkipLink } from "@/components/a11y/skip-link";
import { ActivityBar } from "@/components/layout/activity-bar";
import { HelpOverlay } from "@/components/layout/help-overlay";
import { HeaderBar } from "@/components/layout/header-bar";
import { MobileTabs } from "@/components/layout/mobile-tabs";
import { SessionOverlay } from "@/components/session/SessionOverlay";
import { SessionPicker } from "@/components/session/session-picker";
import { IntegrationImportDialog } from "@/components/board/integration-import-dialog";
import { useEventStream } from "@/lib/hooks/use-event-stream";
import { useIsMobile } from "@/lib/hooks/use-mobile";
import { apiClient } from "@/lib/api/client";
import {
    fetchTasksAtom,
    projectSwitchVersionAtom,
} from "@/lib/atoms/board";
import {
    commandPaletteOpenAtom,
    helpOverlayOpenAtom,
    integrationImportOpenAtom,
    sessionPickerOpenAtom,
} from "@/lib/atoms/ui";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { useSessionOverlay } from "@/lib/hooks/use-session-overlay";

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
    const projectVersion = useAtomValue(projectSwitchVersionAtom);
    const fetchTasks = useSetAtom(fetchTasksAtom);
    const [projectChecked, setProjectChecked] = useState(false);
    const navigateRef = useRef(navigate);
    navigateRef.current = navigate;

    const overlay = useSessionOverlay();
    const workspaceRoute = location.pathname.startsWith("/workspace");

    // Reset project check when project switches (e.g. from welcome page)
    const prevProjectVersionRef = useRef(projectVersion);
    useEffect(() => {
        if (projectVersion !== prevProjectVersionRef.current) {
            prevProjectVersionRef.current = projectVersion;
            setProjectChecked(false);
        }
    }, [projectVersion]);

    // Verify active project before rendering the board.
    useEffect(() => {
        if (projectChecked) return;
        let cancelled = false;
        apiClient
            .getProjects()
            .then((projects) => {
                if (cancelled) return;
                const active = projects.find((p) => p.active);
                if (active) {
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

    const toggleAIPanel = useCallback(() => {
        if (workspaceRoute) return;
        overlay.toggle();
    }, [overlay, workspaceRoute]);

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
                                if (overlay.layout === "fullscreen") {
                                    overlay.setLayout("docked");
                                } else if (overlay.isOpen) {
                                    overlay.setLayout("fullscreen");
                                } else {
                                    overlay.toggle();
                                    overlay.setLayout("fullscreen");
                                }
                            }}
                            aiPanelAvailable={!workspaceRoute}
                            aiPanelOpen={overlay.isOpen}
                            aiPanelFullscreen={
                                !workspaceRoute &&
                                overlay.isOpen &&
                                overlay.layout === "fullscreen"
                            }
                        />
                    )}

                    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
                        <div className="flex min-h-0 min-w-0 flex-1">
                            <main
                                id="main-content"
                                className={cn(
                                    "min-h-0 min-w-0 flex-1 overflow-y-auto bg-[color:var(--surface-0)] pb-[calc(5rem+env(safe-area-inset-bottom))] lg:pb-0",
                                )}
                            >
                                <Outlet />
                            </main>
                        </div>
                    </div>
                </div>

                {isMobile && <MobileTabs />}
            </div>

            <SessionOverlay />
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
