import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Loader2, Play, Square, Clock, Users, Terminal } from "lucide-react";
import { useAtomValue } from "jotai";
import { toast } from "sonner";
import { apiClient } from "@/lib/api/client";
import { sseConnectedAtom } from "@/lib/atoms/connection";
import { cn, asBool, normalizeLauncher } from "@/lib/utils";
import {
    openInEditor,
    launcherDisplayName,
    type LauncherBackend,
} from "@/lib/utils/editor-links";
import { Button } from "@/components/ui/button";
import { AttachedInstructionsDialog, skipAttachedGuidanceAtom } from "@/components/board/attached-instructions-dialog";
import { useAtomValue as useJotaiValue } from "jotai";

// ---------------------------------------------------------------------------
// Terminal attach helpers
// ---------------------------------------------------------------------------

function tmuxAttachCommand(sessionId: string): string {
    const name = `kagan-${sessionId.replaceAll(":", "-")}`;
    return `tmux attach-session -t ${name}`;
}

function nvimAttachCommand(worktreePath: string | null): string {
    if (worktreePath) {
        // quote path segments with spaces
        const quoted = worktreePath.includes(' ') ? `"${worktreePath}"` : worktreePath;
        return `cd ${quoted} && nvim .kagan/start_prompt.md`;
    }
    return "nvim .kagan/start_prompt.md";
}

function terminalAttachCommand(
    launcher: LauncherBackend,
    worktreePath: string | null,
    activeSessionId: string | null,
): string | null {
    if (launcher === "tmux") {
        return activeSessionId ? tmuxAttachCommand(activeSessionId) : null;
    }
    if (launcher === "nvim") {
        return nvimAttachCommand(worktreePath);
    }
    return null;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Component (~80 LOC)
// ---------------------------------------------------------------------------

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
    const skipGuidance = useJotaiValue(skipAttachedGuidanceAtom);

    const isRunning = status === "IN_PROGRESS";
    const hasInteractiveSession = Boolean(activeSessionLauncher);
    const [pending, setPending] = useState<"starting" | "stopping" | null>(null);
    const [elapsed, setElapsed] = useState(0);
    const [fallbackStartedAtMs, setFallbackStartedAtMs] = useState<number | null>(null);
    const [instructionsOpen, setInstructionsOpen] = useState(false);
    const [instructionsLauncher, setInstructionsLauncher] = useState<LauncherBackend>("vscode");
    const lastActionRef = useRef(0);

    const startedAtMs = useMemo(() => {
        if (!startedAt) return null;
        const p = Date.parse(startedAt);
        return Number.isNaN(p) ? null : p;
    }, [startedAt]);
    const effectiveStartMs = startedAtMs ?? fallbackStartedAtMs;

    // Clear pending when status changes
    useEffect(() => { setPending(null); }, [status]);

    // Elapsed timer
    useEffect(() => {
        if (!isRunning) { setFallbackStartedAtMs(null); return; }
        if (startedAtMs === null && fallbackStartedAtMs === null) setFallbackStartedAtMs(Date.now());
    }, [isRunning, startedAtMs, fallbackStartedAtMs]);

    useEffect(() => {
        if (!isRunning || effectiveStartMs === null) { setElapsed(0); return; }
        const calc = () => Math.max(0, Math.floor((Date.now() - effectiveStartMs) / 1000));
        setElapsed(calc());
        const tick = () => { if (document.visibilityState === "visible") setElapsed(calc()); };
        const id = setInterval(tick, 1000);
        document.addEventListener("visibilitychange", tick);
        return () => { clearInterval(id); document.removeEventListener("visibilitychange", tick); };
    }, [isRunning, effectiveStartMs]);

    const formatTime = (secs: number) => {
        const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = secs % 60;
        return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
    };

    const debounce = () => {
        const now = Date.now();
        if (now - lastActionRef.current < 500) return false;
        lastActionRef.current = now;
        return true;
    };

    const startAttachedSession = useCallback(async (launcher: LauncherBackend) => {
        setPending("starting");
        try {
            const started = await apiClient.runTask(taskId, { launcher });
            let wpath = worktreePath ?? null;
            if (!wpath) {
                try { wpath = (await apiClient.getTaskWorktree(taskId)).worktree?.path ?? null; } catch { wpath = null; }
            }
            const cmd = terminalAttachCommand(launcher, wpath, started.active_session?.id ?? null);
            if (cmd) {
                try { await navigator.clipboard.writeText(cmd); toast.success("Interactive session started. Terminal command copied to clipboard."); }
                catch { toast.info(`Interactive session started. Run: ${cmd}`); }
                return;
            }
            if (wpath) {
                if (openInEditor(launcher, wpath)) toast.success(`Opening ${launcherDisplayName(launcher)}...`);
            }
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to start interactive session");
            setPending(null);
        }
    }, [taskId, worktreePath]);

    const handleStart = useCallback(async () => {
        if (!debounce()) return;
        setPending("starting");
        apiClient.runTask(taskId).then(() => setPending(null)).catch((err) => {
            setPending(null);
            toast.error(err instanceof Error ? err.message : "Agent run failed");
        });
    }, [taskId]);

    const handleStop = useCallback(async () => {
        if (!debounce()) return;
        setPending("stopping");
        if (hasInteractiveSession) {
            apiClient.detachTask(taskId).catch((err) => {
                toast.error(err instanceof Error ? err.message : "Failed to detach interactive session");
                setPending(null);
            });
        } else {
            apiClient.cancelTask(taskId).then(() => setPending(null)).catch((err) => {
                setPending(null);
                toast.error(err instanceof Error ? err.message : "Failed to stop agent");
            });
        }
    }, [taskId, hasInteractiveSession]);

    const handleAttach = useCallback(async () => {
        if (!debounce()) return;
        try {
            const settings = await apiClient.getSettings();
            const launcherNorm = normalizeLauncher(
                taskLauncher?.trim().toLowerCase() || settings.attached_launcher || attachedLauncher || "vscode",
            );
            if (isRunning && hasInteractiveSession) {
                const cmd = terminalAttachCommand(launcherNorm, worktreePath ?? null, activeSessionId ?? null);
                if (cmd) {
                    try { await navigator.clipboard.writeText(cmd); toast.success("Attach command copied to clipboard"); }
                    catch { toast.info(cmd); }
                    return;
                }
                if (worktreePath && openInEditor(launcherNorm, worktreePath)) {
                    toast.success(`Opening ${launcherDisplayName(launcherNorm)}...`);
                }
                return;
            }
            if (isRunning && !hasInteractiveSession) {
                try { await apiClient.cancelTask(taskId); }
                catch { toast.error("Failed to stop managed agent before attaching."); return; }
            }
            const skipServer = asBool(settings.skip_attached_instructions_popup, false);
            if (skipServer || skipGuidance) {
                await startAttachedSession(launcherNorm);
                return;
            }
            setInstructionsLauncher(launcherNorm);
            setInstructionsOpen(true);
        } catch (err) {
            toast.error(err instanceof Error ? err.message : "Failed to attach interactive session");
            setPending(null);
        }
    }, [activeSessionId, attachedLauncher, hasInteractiveSession, isRunning, startAttachedSession, taskId, taskLauncher, worktreePath, skipGuidance]);

    const isBusy = pending !== null;

    return (
        <div className={cn("flex items-center gap-2", className)}>
            {isRunning || pending === "starting" ? (
                <>
                    <Button size={buttonSize} onClick={handleStop} disabled={!sseConnected || isBusy}>
                        {pending === "stopping" ? <Loader2 className="size-3 animate-spin" /> : <Square className="size-3" />}
                        {pending === "stopping" ? "Stopping..." : hasInteractiveSession ? "Detach" : "Stop"}
                    </Button>
                    <Button variant="secondary" size={buttonSize} onClick={handleAttach} disabled={!sseConnected || isBusy}>
                        <Terminal className="size-3" />
                        Attach
                    </Button>
                    {isRunning && (
                        <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                            <Clock className="size-3" aria-hidden="true" />
                            <span aria-label={`Running for ${formatTime(elapsed)}`}>{formatTime(elapsed)}</span>
                        </span>
                    )}
                    {pending === "starting" && !isRunning && (
                        <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                            <Loader2 className="size-3 animate-spin" aria-hidden="true" />
                            Provisioning...
                        </span>
                    )}
                </>
            ) : (
                <>
                    <Button variant="secondary" size={buttonSize} onClick={handleStart} disabled={!sseConnected || status === "DONE" || isBusy}>
                        <Play className="size-3" />
                        Start
                    </Button>
                    <Button variant="secondary" size={buttonSize} onClick={handleAttach} disabled={!sseConnected || status === "DONE" || isBusy}>
                        <Users className="size-3" />
                        Attach
                    </Button>
                </>
            )}

            <AttachedInstructionsDialog
                open={instructionsOpen}
                onOpenChange={setInstructionsOpen}
                launcher={instructionsLauncher}
                isRunningBackground={isRunning && !hasInteractiveSession}
                onContinue={async (_skipFuture) => {
                    // skipFuture is handled inside the atom via the dialog's switch
                    await startAttachedSession(instructionsLauncher);
                }}
            />
        </div>
    );
}
