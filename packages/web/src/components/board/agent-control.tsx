import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
    Loader2,
    Play,
    Square,
    Clock,
    Users,
    ExternalLink,
    Terminal,
} from "lucide-react";
import { useAtomValue } from "jotai";
import { toast } from "sonner";
import { apiClient } from "@/lib/api/client";
import { kaganWs, type WsInboundMessage } from "@/lib/api/websocket";
import { wsConnectedAtom } from "@/lib/atoms/connection";
import { cn } from "@/lib/utils";
import {
    openInEditor,
    buildEditorLink,
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

const LAUNCHER_BACKENDS: readonly LauncherBackend[] = [
    "tmux",
    "nvim",
    "vscode",
    "cursor",
    "windsurf",
    "kiro",
    "antigravity",
];

function asBool(value: string | undefined, fallback: boolean): boolean {
    if (value === undefined) return fallback;
    return !["0", "false", "no", "off"].includes(value.trim().toLowerCase());
}

function normalizeLauncher(value: string | null | undefined): LauncherBackend {
    if (!value) return "vscode";
    const normalized = value.trim().toLowerCase();
    return LAUNCHER_BACKENDS.includes(normalized as LauncherBackend)
        ? (normalized as LauncherBackend)
        : "vscode";
}

function quoteShell(value: string): string {
    return `"${value.replace(/["\\$`]/g, "\\$&")}"`;
}

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
    executionMode?: string;
    startedAt?: string | null;
    buttonSize?: "xs" | "sm";
    className?: string;
    worktreePath?: string | null;
    pairLauncher?: string | null;
    /** Per-task launcher override (task.launcher). Takes priority over pairLauncher (settings). */
    taskLauncher?: string | null;
}

export function AgentControl({
    taskId,
    status,
    executionMode,
    startedAt,
    buttonSize = "xs",
    className,
    worktreePath,
    pairLauncher,
    taskLauncher,
}: AgentControlProps) {
    const wsConnected = useAtomValue(wsConnectedAtom);
    const isRunning = status === "IN_PROGRESS";
    const [pending, setPending] = useState<"starting" | "stopping" | null>(
        null,
    );
    const lastActionTimeRef = useRef(0);
    const [elapsed, setElapsed] = useState(0);
    const [fallbackStartedAtMs, setFallbackStartedAtMs] = useState<
        number | null
    >(null);
    const [pairInstructionsOpen, setPairInstructionsOpen] = useState(false);
    const [pairInstructionsLauncher, setPairInstructionsLauncher] =
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

    // Listen for WS responses to give immediate feedback
    useEffect(() => {
        const cleanups = [
            kaganWs.on("RUN_STARTED", (data: WsInboundMessage) => {
                if (data.task_id === taskId) setPending(null);
            }),
            kaganWs.on("RUN_CANCELLED", (data: WsInboundMessage) => {
                if (data.task_id === taskId) setPending(null);
            }),
            kaganWs.on("RUN_ERROR", (data: WsInboundMessage) => {
                if (data.task_id === taskId) {
                    setPending(null);
                    toast.error(
                        typeof data.error === "string"
                            ? data.error
                            : "Agent run failed",
                    );
                }
            }),
        ];
        return () => cleanups.forEach((fn) => fn());
    }, [taskId]);

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

    const isPair = executionMode === "PAIR";

    const startPairSession = useCallback(
        async (launcher: LauncherBackend, persistSkipInstructions: boolean) => {
            setPending("starting");
            try {
                if (persistSkipInstructions) {
                    await apiClient.setSettings({
                        skip_pair_instructions_popup: "true",
                    });
                }

                const pairTask = await apiClient.pairTask(taskId);
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
                    pairTask.active_session?.id ?? null,
                );

                if (attachCommand) {
                    try {
                        await navigator.clipboard.writeText(attachCommand);
                        toast.success(
                            "PAIR started. Terminal command copied to clipboard.",
                        );
                    } catch {
                        toast.info(`PAIR started. Run: ${attachCommand}`);
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
                        : "Failed to start pair session",
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

        if (isPair) {
            try {
                const settings = await apiClient.getSettings();
                const taskLauncherNorm = taskLauncher?.trim().toLowerCase();
                const launcher = normalizeLauncher(
                    taskLauncherNorm ||
                        settings.pair_launcher ||
                        pairLauncher ||
                        "vscode",
                );
                const skipInstructions = asBool(
                    settings.skip_pair_instructions_popup,
                    false,
                );
                if (skipInstructions) {
                    await startPairSession(launcher, false);
                    return;
                }
                setPairInstructionsLauncher(launcher);
                setSkipGuidanceForFuture(false);
                setPairInstructionsOpen(true);
            } catch (err) {
                toast.error(
                    err instanceof Error
                        ? err.message
                        : "Failed to start pair session",
                );
                setPending(null);
            }
        } else {
            setPending("starting");
            kaganWs.startRun(taskId);
        }
    }, [isPair, pairLauncher, startPairSession, taskId]);

    const handleStop = useCallback(async () => {
        // 2.1: Debounce rapid start/stop clicks (500ms)
        const now = Date.now();
        if (now - lastActionTimeRef.current < 500) return;
        lastActionTimeRef.current = now;

        setPending("stopping");
        if (isPair) {
            try {
                await apiClient.endPairing(taskId);
            } catch (err) {
                toast.error(
                    err instanceof Error
                        ? err.message
                        : "Failed to end pair session",
                );
                setPending(null);
            }
        } else {
            kaganWs.cancelRun(taskId);
        }
    }, [taskId, isPair]);

    const isBusy = pending !== null;

    return (
        <div className={cn("flex items-center gap-2", className)}>
            {isRunning || pending === "starting" ? (
                <>
                    <Button
                        size={buttonSize}
                        onClick={handleStop}
                        disabled={!wsConnected || isBusy}
                    >
                        {pending === "stopping" ? (
                            <Loader2 className="size-3 animate-spin" />
                        ) : (
                            <Square className="size-3" />
                        )}
                        {pending === "stopping" ? "Stopping..." : "Stop"}
                    </Button>
                    {isPair &&
                        isRunning &&
                        worktreePath &&
                        (() => {
                            const launcher = (pairLauncher ||
                                "vscode") as LauncherBackend;
                            const link = buildEditorLink(
                                launcher,
                                worktreePath,
                            );

                            if (link.supportsDeepLink) {
                                return (
                                    <Button
                                        variant="secondary"
                                        size={buttonSize}
                                        onClick={() =>
                                            openInEditor(launcher, worktreePath)
                                        }
                                    >
                                        <ExternalLink className="size-3" />
                                        {link.label}
                                    </Button>
                                );
                            }

                            return (
                                <Button
                                    variant="secondary"
                                    size={buttonSize}
                                    onClick={() => {
                                        if (link.fallbackMessage) {
                                            navigator.clipboard
                                                .writeText(link.fallbackMessage)
                                                .then(
                                                    () =>
                                                        toast.info(
                                                            "Terminal command copied to clipboard",
                                                        ),
                                                    () =>
                                                        toast.info(
                                                            link.fallbackMessage!,
                                                        ),
                                                );
                                        }
                                    }}
                                    title={link.fallbackMessage ?? undefined}
                                >
                                    <Terminal className="size-3" />
                                    {link.label}
                                </Button>
                            );
                        })()}
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
                <Button
                    variant="secondary"
                    size={buttonSize}
                    onClick={handleStart}
                    disabled={!wsConnected || status === "DONE" || isBusy}
                >
                    {isPair ? (
                        <Users className="size-3" />
                    ) : (
                        <Play className="size-3" />
                    )}
                    {isPair ? "Pair" : "Start"}
                </Button>
            )}

            <Dialog
                open={pairInstructionsOpen}
                onOpenChange={setPairInstructionsOpen}
            >
                <DialogContent className="sm:max-w-xl">
                    <DialogHeader>
                        <DialogTitle>PAIR Session Instructions</DialogTitle>
                        <DialogDescription>
                            We will start a PAIR session, then you continue in
                            your own terminal/editor using the task startup
                            prompt.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-3 text-sm text-[var(--muted-foreground)]">
                        {pairInstructionsLauncher === "tmux" ? (
                            <>
                                <p>
                                    You are about to enter a tmux-backed PAIR
                                    session.
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
                        ) : pairInstructionsLauncher === "nvim" ? (
                            <>
                                <p>
                                    PAIR will open Neovim with the startup
                                    prompt file.
                                </p>
                                <ol className="list-decimal space-y-1 pl-5">
                                    <li>
                                        Press Continue to prepare the PAIR
                                        session.
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
                                    PAIR will open{" "}
                                    {launcherDisplayName(
                                        pairInstructionsLauncher,
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
                                aria-label="Do not show pair guidance again"
                            />
                        </label>
                    </div>

                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => {
                                setPairInstructionsOpen(false);
                            }}
                        >
                            Cancel
                        </Button>
                        <Button
                            onClick={() => {
                                setPairInstructionsOpen(false);
                                void startPairSession(
                                    pairInstructionsLauncher,
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
