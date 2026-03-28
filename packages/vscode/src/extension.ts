import * as vscode from "vscode";
import { KaganClient } from "./api/client.js";
import { SSEStream } from "./api/sse.js";
import { registerReviewCommands } from "./commands/review.js";
import { registerSettingsCommands } from "./commands/settings.js";
import { registerTaskCommands } from "./commands/tasks.js";
import { BoardTreeProvider } from "./providers/board.tree.js";
import { AgentOutputProvider } from "./providers/events.output.js";
import {
  KaganDiffContentProvider,
  TaskScmProvider,
} from "./providers/tasks.scm.js";
import { ReviewCommentProvider, ReviewDocumentProvider } from "./providers/review.comments.js";
import { AgentTerminalProvider } from "./providers/tasks.terminal.js";
import { registerChatParticipant } from "./providers/chat.participant.js";
import { StatusBar } from "./status/bar.js";
import { SSE_TYPE, type SSEMessage } from "./api/types.js";
import { LocalServerSupervisor } from "./server/supervisor.js";

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration("kagan");
  const serverUrl = config.get<string>("serverUrl", "localhost:8765").replace(/^(https?:\/\/)/, "");
  const protocol = config.get<"http" | "https">("protocol", "http");
  const token = config.get<string>("authToken", "");

  const client = new KaganClient(serverUrl, protocol, token || undefined);
  const sse = new SSEStream(client.getHostPort());
  sse.setProtocol(protocol);
  if (token) sse.setToken(token);
  const boardProvider = new BoardTreeProvider(client);
  const scmProvider = new TaskScmProvider(client);
  const diffProvider = new KaganDiffContentProvider(client);
  const outputProvider = new AgentOutputProvider(client);
  const reviewDocumentProvider = new ReviewDocumentProvider();
  const reviewProvider = new ReviewCommentProvider();
  const terminalProvider = new AgentTerminalProvider(client);
  const statusBar = new StatusBar();
  const serverLog = vscode.window.createOutputChannel("Kagan Server");
  const serverSupervisor = new LocalServerSupervisor(serverLog);

  const boardView = vscode.window.createTreeView("kagan.board", {
    treeDataProvider: boardProvider,
    showCollapseAll: true,
  });

  const diffRegistration = vscode.workspace.registerTextDocumentContentProvider(
    "kagan-diff",
    diffProvider,
  );
  const reviewRegistration = vscode.workspace.registerTextDocumentContentProvider(
    "kagan-review",
    reviewDocumentProvider,
  );

  const connectCommand = vscode.commands.registerCommand("kagan.connect", async () => {
    await connect(
      client,
      sse,
      boardProvider,
      statusBar,
      serverLog,
      serverSupervisor,
      getServerLaunchSettings(),
    );
  });

  const disconnectCommand = vscode.commands.registerCommand("kagan.disconnect", async () => {
    sse.stop();
    await vscode.commands.executeCommand("setContext", "kagan.connected", false);
    statusBar.showDisconnected();
  });

  const refreshCommand = vscode.commands.registerCommand("kagan.board.refresh", async () => {
    await refreshBoard(client, boardProvider, statusBar);
  });

  registerTaskCommands(
    context,
    client,
    boardProvider,
    outputProvider,
    scmProvider,
    reviewProvider,
    terminalProvider,
  );
  registerReviewCommands(context, client, boardProvider, reviewProvider);
  registerSettingsCommands(context, client);
  registerChatParticipant(context, client, sse);

  const messageSubscription = sse.onMessage((message: SSEMessage) => {
    boardProvider.onSSE(message);
    outputProvider.onSSE(message);

    if (message.type === SSE_TYPE.TASK_UPDATED) {
      void refreshCounts(client, statusBar);
    }
  });

  const connectedSubscription = sse.onConnected((connected) => {
    if (!connected) {
      void vscode.commands.executeCommand("setContext", "kagan.connected", false);
      statusBar.showDisconnected();
      return;
    }

    void vscode.commands.executeCommand("setContext", "kagan.connected", true);
    void refreshBoard(client, boardProvider, statusBar);
  });

  const configSubscription = vscode.workspace.onDidChangeConfiguration((event) => {
    if (
      !event.affectsConfiguration("kagan.serverUrl") &&
      !event.affectsConfiguration("kagan.protocol") &&
      !event.affectsConfiguration("kagan.authToken")
    ) {
      return;
    }

    const cfg = vscode.workspace.getConfiguration("kagan");
    const nextUrl = cfg.get<string>("serverUrl", "localhost:8765").replace(/^(https?:\/\/)/, "");
    const nextProtocol = cfg.get<"http" | "https">("protocol", "http");
    const nextToken = cfg.get<string>("authToken", "");

    client.setBaseUrl(nextUrl);
    client.setProtocol(nextProtocol);
    client.setToken(nextToken || undefined);

    sse.setBaseUrl(nextUrl);
    sse.setProtocol(nextProtocol);
    sse.setToken(nextToken || undefined);

    sse.stop();
    sse.start();
  });

  context.subscriptions.push(
    boardView,
    diffRegistration,
    reviewRegistration,
    connectCommand,
    disconnectCommand,
    refreshCommand,
    messageSubscription,
    connectedSubscription,
    configSubscription,
    sse,
    scmProvider,
    outputProvider,
    reviewProvider,
    statusBar,
    serverLog,
    serverSupervisor,
  );

  statusBar.showDisconnected();
  void vscode.commands.executeCommand("setContext", "kagan.connected", false);

  if (config.get<boolean>("autoConnect", true)) {
    void connect(
      client,
      sse,
      boardProvider,
      statusBar,
      serverLog,
      serverSupervisor,
      getServerLaunchSettings(),
    );
  }

  void detectAttachContext(client, sse);

  function getServerLaunchSettings(): { autoStartServer: boolean; serverCommand: string } {
    const nextConfig = vscode.workspace.getConfiguration("kagan");
    return {
      autoStartServer: nextConfig.get<boolean>("autoStartServer", true),
      serverCommand: nextConfig.get<string>("serverCommand", "kagan").trim() || "kagan",
    };
  }
}

export function deactivate(): undefined {
  return undefined;
}

async function connect(
  client: KaganClient,
  sse: SSEStream,
  boardProvider: BoardTreeProvider,
  statusBar: StatusBar,
  serverLog: vscode.OutputChannel,
  serverSupervisor: LocalServerSupervisor,
  launchSettings: {
    autoStartServer: boolean;
    serverCommand: string;
  },
): Promise<void> {
  statusBar.showConnecting();

  try {
    let reachable = await client.ping();
    if (!reachable && launchSettings.autoStartServer) {
      await serverSupervisor.ensureRunning(client, launchSettings.serverCommand);
      reachable = await client.ping();
    }
    if (!reachable) {
      throw new Error("Cannot reach Kagan server");
    }

    await client.verifyApi();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    statusBar.showError(message);
    const choice = await vscode.window.showErrorMessage(message, "Show Server Log");
    if (choice === "Show Server Log") {
      serverLog.show(true);
    }
    await vscode.commands.executeCommand("setContext", "kagan.connected", false);
    return;
  }

  await vscode.commands.executeCommand("setContext", "kagan.connected", true);
  sse.start();
  await refreshBoard(client, boardProvider, statusBar);
}

async function refreshBoard(
  client: KaganClient,
  boardProvider: BoardTreeProvider,
  statusBar: StatusBar,
): Promise<void> {
  await refreshCounts(client, statusBar);
  boardProvider.refresh();
}

async function refreshCounts(client: KaganClient, statusBar: StatusBar): Promise<void> {
  try {
    const counts = await client.getTaskCounts();
    statusBar.showConnected(counts);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    statusBar.showError(message);
  }
}

async function detectAttachContext(client: KaganClient, sse: SSEStream): Promise<void> {
  const config = vscode.workspace.getConfiguration("kagan");
  if (!config.get<boolean>("autoWatchOnAttach", true)) return;

  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) return;

  const contextUri = vscode.Uri.joinPath(folders[0].uri, ".kagan", "attach_context.json");

  try {
    await vscode.workspace.fs.stat(contextUri);
  } catch {
    return;
  }

  let context: { task_id?: string; session_id?: string };
  try {
    const raw = await vscode.workspace.fs.readFile(contextUri);
    context = JSON.parse(new TextDecoder().decode(raw));
  } catch (error) {
    console.warn("[kagan] Failed to read attach context:", error);
    return;
  }

  if (!context.task_id) return;

  const taskId = context.task_id;

  // Wait for SSE connection (with timeout) before checking task state
  await Promise.race([
    new Promise<void>((resolve) => {
      const disposable = sse.onConnected((connected) => {
        if (connected) { disposable.dispose(); resolve(); }
      });
    }),
    new Promise<void>((_, reject) =>
      setTimeout(() => reject(new Error("SSE connection timeout")), 10_000),
    ),
  ]).catch(() => {});

  let task: Awaited<ReturnType<KaganClient["getTask"]>>;
  try {
    task = await client.getTask(taskId);
    if (task.status !== "IN_PROGRESS") return;
  } catch {
    return;
  }

  await vscode.commands.executeCommand("kagan.chat.open", {
    kind: "task",
    task: {
      id: task.id,
      title: task.title,
    },
  });
}
