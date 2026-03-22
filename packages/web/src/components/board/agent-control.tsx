import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
    Loader2,
    Play,
    Square,
    Clock,
    Users,
    Terminal,
} from "lucide-react";
import { useAtomValue } from "jotai";
import { toast } from "sonner";
import { apiClient } from "@/lib/api/client";
import { sseConnectedAtom } from "@/lib/atoms/connection";
import { cn, asBool, normalizeLauncher, quoteShell } from "@/lib/utils";
import {
    openInEditor,
    launcherDisplayName,
    type LauncherBackend,
} from "@/lib/utils/editor-links";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";


function tmuxSessionName(sessionId: string): string {
    return `kagan-${sessionId.replaceAll(":", "-")}`;
}

function terminalAttachCommand(
    launcher: LauncherBackend,
    worktreePath: string | null,
    activeSessionId: string | null,
): string | null {
    if (launcher === "tmux") {
        if (!activeSessionId) return null;
        return `tmux attach-session -t ${tmuxSessionName(activeSessionId)}`;
    }
    if (launcher === "nvim") {
        if (worktreePath) {
            return `cd ${quoteShell(worktreePath)} && nvim .kagan/start_prompt.md`;
        }
        return "nvim .kagan/start_prompt.md";
    }
    return null;
}

interface AgentControlProps {
    taskId: string;
    status: string;
    activeSessionId?: string | null;
    activeSessionLauncher?: string | null;
    startedAt?: string | null;
    buttonSize?: "xs" | "sm";
    className?: string;
    worktreePath?: string | null;
    attachedLauncher?: string | null;
    /** Per-task launcher override (task.launcher). Takes priority over attachedLauncher (settings). */
    taskLauncher?: string | null;
}

export function AgentControl({
    taskId,
    status,
    activeSessionId,
    activeSessionLauncher,
    startedAt,
    buttonSize = "xs",
    className,
    worktreePath,
    attachedLauncher,
    taskLauncher,
}: AgentControlProps) {
    const sseConnected = useAtomValue(sseConnectedAtom);
    const isRunning = status === "IN_PROGRESS";
    const [pending, setPending] = useState<"starting" | "stopping" | null>(
        null,
    );
    const lastActionTimeRef = useRef(0);
    const [elapsed, setElapsed] = useState(0);
    const [fallbackStartedAtMs, setFallbackStartedAtMs] = useState<
        number | null
    >(null);
    const [attachedInstructionsOpen, setAttachedInstructionsOpen] = useState(false);
    const [attachedInstructionsLauncher, setAttachedInstructionsLauncher] =
        useState<LauncherBackend>("vscode");
    const [skipGuidanceForFuture, setSkipGuidanceForFuture] = useState(false);

    const startedAtMs = useMemo(() => {
        if (!startedAt) return null;
        const parsed = Date.parse(startedAt);
        return Number.isNaN(parsed) ? null : parsed;
    }, [startedAt]);
    const effectiveStartedAtMs = startedAtMs ?? fallbackStartedAtMs;

    // Clear pending state when status actually changes
    useEffect(() => {
        setPending(null);
    }, [status]);

    // No WS listeners needed — start/stop are REST calls that resolve directly

    // Elapsed timer
    const computeElapsed = useCallback(() => {
        if (!isRunning || effectiveStartedAtMs === null) return 0;
        return Math.max(
            0,
            Math.floor((Date.now() - effectiveStartedAtMs) / 1000),
        );
    }, [isRunning, effectiveStartedAtMs]);

    useEffect(() => {
        if (!isRunning) {
            setFallbackStartedAtMs(null);
            return;
        }
        if (startedAtMs === null && fallbackStartedAtMs === null) {
            setFallbackStartedAtMs(Date.now());
        }
    }, [isRunning, startedAtMs, fallbackStartedAtMs]);

    useEffect(() => {
        if (!isRunning || effectiveStartedAtMs === null) {
            setElapsed(0);
            return;
        }
        setElapsed(computeElapsed());
        // 4.3: Pause elapsed timer when tab is hidden
        const tick = () => {
            if (document.visibilityState === "visible")
                setElapsed(computeElapsed());
        };
        const interval = setInterval(tick, 1000);
        // Recalculate immediately when tab becomes visible again
        const onVisible = () => {
            if (document.visibilityState === "visible")
                setElapsed(computeElapsed());
        };
        document.addEventListener("visibilitychange", onVisible);
        return () => {
            clearInterval(interval);
            document.removeEventListener("visibilitychange", onVisible);
        };
    }, [isRunning, effectiveStartedAtMs, computeElapsed]);

    const formatTime = (secs: number) => {
        const h = Math.floor(secs / 3600);
        const m = Math.floor((secs % 3600) / 60);
        const s = secs % 60;
        if (h > 0) {
            return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
        }
        return `${m}:${String(s).padStart(2, "0")}`;
    };

    const hasInteractiveSession = Boolean(activeSessionLauncher);

    const startAttachedSession = useCallback(
        async (launcher: LauncherBackend, persistSkipInstructions: boolean) => {
            setPending("starting");
            try {
                if (persistSkipInstructions) {
                    await apiClient.setSettings({
                        skip_attached_instructions_popup: "true",
                    });
                }

                const startedTask = await apiClient.runTask(taskId, {
                    launcher,
                });
                let effectiveWorktreePath = worktreePath ?? null;
                if (!effectiveWorktreePath) {
                    try {
                        const worktree =
                            await apiClient.getTaskWorktree(taskId);
                        effectiveWorktreePath = worktree.worktree?.path ?? null;
                    } catch {
                        effectiveWorktreePath = null;
                    }
                }

                const attachCommand = terminalAttachCommand(
                    launcher,
                    effectiveWorktreePath,
                    startedTask.active_session?.id ?? null,
                );

                if (attachCommand) {
                    try {
                        await navigator.clipboard.writeText(attachCommand);
                        toast.success(
                            "Interactive session started. Terminal command copied to clipboard.",
                        );
                    } catch {
                        toast.info(`Interactive session started. Run: ${attachCommand}`);
                    }
                    return;
                }

                if (effectiveWorktreePath) {
                    const opened = openInEditor(
                        launcher,
                        effectiveWorktreePath,
                    );
                    if (opened) {
                        toast.success(
                            `Opening ${launcherDisplayName(launcher)}...`,
                        );
                    }
                }
            } catch (err) {
                toast.error(
                    err instanceof Error
                        ? err.message
                        : "Failed to start interactive session",
                );
                setPending(null);
            }
        },
        [taskId, worktreePath],
    );

    const handleStart = useCallback(async () => {
        // 2.1: Debounce rapid start/stop clicks (500ms)
        const now = Date.now();
        if (now - lastActionTimeRef.current < 500) return;
        lastActionTimeRef.current = now;

        setPending("starting");
        apiClient
            .runTask(taskId)
            .then(() => setPending(null))
            .catch((err) => {
                setPending(null);
                toast.error(err instanceof Error ? err.message : "Agent run failed");
            });
    }, [taskId]);

    const handleAttach = useCallback(async () => {
        const now = Date.now();
        if (now - lastActionTimeRef.current < 500) return;
        lastActionTimeRef.current = now;

        try {
            const settings = await apiClient.getSettings();
            const taskLauncherNorm = taskLauncher?.trim().toLowerCase();
            const launcher = normalizeLauncher(
                taskLauncherNorm ||
                    settings.attached_launcher ||
                    attachedLauncher ||
                    "vscode",
            );

            if (isRunning && hasInteractiveSession) {
                const attachCommand = terminalAttachCommand(
                    launcher,
                    worktreePath ?? null,
                    activeSessionId ?? null,
                );
                if (attachCommand) {
                    try {
                        await navigator.clipboard.writeText(attachCommand);
                        toast.success("Attach command copied to clipboard");
                    } catch {
                        toast.info(attachCommand);
                    }
                    return;
                }
                if (worktreePath) {
                    const opened = openInEditor(launcher, worktreePath);
                    if (opened) {
                        toast.success(`Opening ${launcherDisplayName(launcher)}...`);
                    }
                }
                return;
            }

            if (isRunning && !hasInteractiveSession) {
                try {
                    await apiClient.cancelTask(taskId);
                } catch {
                    toast.error("Failed to stop managed agent before attaching.");
                    return;
                }
            }

            const skipInstructions = asBool(settings.skip_attached_instructions_popup, false);
            if (skipInstructions) {
                await startAttachedSession(launcher, false);
                return;
            }
            setAttachedInstructionsLauncher(launcher);
            setSkipGuidanceForFuture(false);
            setAttachedInstructionsOpen(true);
        } catch (err) {
            toast.error(
                err instanceof Error ? err.message : "Failed to attach interactive session",
            );
            setPending(null);
        }
    }, [
        activeSessionId,
        attachedLauncher,
        hasInteractiveSession,
        isRunning,
        startAttachedSession,
        taskLauncher,
        worktreePath,
    ]);

    const handleStop = useCallback(async () => {
        // 2.1: Debounce rapid start/stop clicks (500ms)
        const now = Date.now();
        if (now - lastActionTimeRef.current < 500) return;
        lastActionTimeRef.current = now;

        setPending("stopping");
        if (hasInteractiveSession) {
            try {
                await apiClient.detachTask(taskId);
            } catch (err) {
                toast.error(
                    err instanceof Error
                        ? err.message
                        : "Failed to detach interactive session",
                );
                setPending(null);
            }
        } else {
            apiClient.cancelTask(taskId)
                .then(() => setPending(null))
                .catch((err) => {
                    setPending(null);
                    toast.error(err instanceof Error ? err.message : "Failed to stop agent");
                });
        }
    }, [taskId, hasInteractiveSession]);

    const isBusy = pending !== null;

    return (
        <div className={cn("flex items-center gap-2", className)}>
            {isRunning || pending === "starting" ? (
                <>
                    <Button
                        size={buttonSize}
                        onClick={handleStop}
                        disabled={!sseConnected || isBusy}
                    >
                        {pending === "stopping" ? (
                            <Loader2 className="size-3 animate-spin" />
                        ) : (
                            <Square className="size-3" />
                        )}
                        {pending === "stopping"
                            ? "Stopping..."
                            : hasInteractiveSession
                              ? "Detach"
                              : "Stop"}
                    </Button>
                    {hasInteractiveSession ? (
                        <Button
                            variant="secondary"
                            size={buttonSize}
                            onClick={handleAttach}
                            disabled={!sseConnected || isBusy}
                        >
                            <Terminal className="size-3" />
                            Attach
                        </Button>
                    ) : null}
                    {isRunning && (
                        <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                            <Clock className="size-3" />
                            {formatTime(elapsed)}
                        </span>
                    )}
                    {pending === "starting" && !isRunning && (
                        <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                            <Loader2 className="size-3 animate-spin" />
                            Provisioning...
                        </span>
                    )}
                </>
            ) : (
                <>
                    <Button
                        variant="secondary"
                        size={buttonSize}
                        onClick={handleStart}
                        disabled={!sseConnected || status === "DONE" || isBusy}
                    >
                        <Play className="size-3" />
                        Start
                    </Button>
                    <Button
                        variant="secondary"
                        size={buttonSize}
                        onClick={handleAttach}
                        disabled={!sseConnected || status === "DONE" || isBusy}
                    >
                        <Users className="size-3" />
                        Attach
                    </Button>
                </>
            )}

            <Dialog
                open={attachedInstructionsOpen}
                onOpenChange={setAttachedInstructionsOpen}
            >
                <DialogContent className="sm:max-w-xl">
                    <DialogHeader>
                        <DialogTitle>Interactive Session Instructions</DialogTitle>
                        <DialogDescription>
                            {isRunning && !hasInteractiveSession
                                ? "A background agent is running. It will be stopped and you will take over manually in your terminal/editor."
                                : "We will start an interactive session, then you continue in your own terminal/editor using the task startup prompt."}
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-3 text-sm text-[var(--muted-foreground)]">
                        {attachedInstructionsLauncher === "tmux" ? (
                            <>
                                <p>
                                    You are about to enter a tmux-backed interactive session.
                                </p>
                                <ol className="list-decimal space-y-1 pl-5">
                                    <li>
                                        Press Continue to launch the agent
                                        session.
                                    </li>
                                    <li>
                                        A tmux attach command is copied to your
                                        clipboard.
                                    </li>
                                    <li>
                                        Open your terminal and paste the command
                                        to attach.
                                    </li>
                                    <li>
                                        Detach with <code>Ctrl+b d</code> to
                                        return to Kagan.
                                    </li>
                                </ol>
                            </>
                        ) : attachedInstructionsLauncher === "nvim" ? (
                            <>
                                <p>
                                    Interactive attach will open Neovim with the startup prompt file.
                                </p>
                                <ol className="list-decimal space-y-1 pl-5">
                                    <li>
                                        Press Continue to prepare the interactive session.
                                    </li>
                                    <li>
                                        Neovim opens with{" "}
                                        <code>.kagan/start_prompt.md</code> in
                                        the task worktree.
                                    </li>
                                    <li>
                                        Copy the prompt contents and paste into
                                        your AI chat plugin.
                                    </li>
                                </ol>
                            </>
                        ) : (
                            <>
                                <p>
                                    Interactive attach will open{" "}
                                    {launcherDisplayName(
                                        attachedInstructionsLauncher,
                                    )}{" "}
                                    in the task worktree. The startup prompt
                                    file will be open in your editor.
                                </p>
                                <ol className="list-decimal space-y-1 pl-5">
                                    <li>
                                        Press Continue to start the session.
                                    </li>
                                    <li>
                                        Kagan opens your editor in the task
                                        worktree with the startup prompt
                                        visible.
                                    </li>
                                    <li>
                                        Copy the prompt contents and paste into
                                        your IDE's AI chat.
                                    </li>
                                </ol>
                            </>
                        )}

                        <label className="flex items-center justify-between gap-3 rounded border border-[color:var(--border-subtle)] px-3 py-2">
                            <span className="text-sm text-[var(--foreground)]">
                                Do not show this guidance again
                            </span>
                            <Switch
                                checked={skipGuidanceForFuture}
                                onCheckedChange={(value) =>
                                    setSkipGuidanceForFuture(Boolean(value))
                                }
                                aria-label="Do not show attached guidance again"
                            />
                        </label>
                    </div>

                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => {
                                setAttachedInstructionsOpen(false);
                            }}
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={() => {
                                setAttachedInstructionsOpen(false);
                                void startAttachedSession(
                                    attachedInstructionsLauncher,
                                    skipGuidanceForFuture,
                                );
                            }}
                        >
                            Continue
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
