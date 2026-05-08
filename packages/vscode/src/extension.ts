import * as vscode from "vscode";
import { KaganClient } from "./api/client.js";
import { SSEStream } from "./api/sse.js";
import { registerAnalyticsCommands } from "./commands/analytics.js";
import { registerIntegrationCommands } from "./commands/integrations.js";
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
import { SessionsTreeProvider } from "./providers/sessions.tree.js";
import { DoctorStatusProvider } from "./providers/doctor.status.js";
import { MentionCompletionProvider } from "./providers/mention-completion-provider.js";
import { MentionLinkProvider } from "./providers/mention-link-provider.js";
import { StatusBar } from "./status/bar.js";
import { SSE_TYPE, type SSEMessage } from "@kagan/shared-api-client";
import { LocalServerSupervisor } from "./server/supervisor.js";

let activeServerSupervisor: LocalServerSupervisor | null = null;

function readConnectionConfig(): { serverUrl: string; protocol: "http" | "https"; authToken: string } {
  const cfg = vscode.workspace.getConfiguration("kagan");
  return {
    serverUrl: cfg.get<string>("serverUrl", "localhost:8765").replace(/^(https?:\/\/)/, ""),
    protocol: cfg.get<"http" | "https">("protocol", "http"),
    authToken: cfg.get<string>("authToken", ""),
  };
}

export function activate(context: vscode.ExtensionContext): void {
  const { serverUrl, protocol, authToken: token } = readConnectionConfig();

  const client = new KaganClient(serverUrl, protocol, token || undefined);
  const sse = new SSEStream(client);
  const boardProvider = new BoardTreeProvider(client);
  const scmProvider = new TaskScmProvider(client);
  const diffProvider = new KaganDiffContentProvider(client);
  const outputProvider = new AgentOutputProvider(client);
  const reviewDocumentProvider = new ReviewDocumentProvider();
  const reviewProvider = new ReviewCommentProvider(reviewDocumentProvider);
  const terminalProvider = new AgentTerminalProvider(client);
  const statusBar = new StatusBar();
  const doctorStatus = new DoctorStatusProvider(client, statusBar);
  const serverLog = vscode.window.createOutputChannel("Kagan Server");
  const serverSupervisor = new LocalServerSupervisor(serverLog);
  activeServerSupervisor = serverSupervisor;

  const sessionsProvider = new SessionsTreeProvider(client);

  const boardView = vscode.window.createTreeView("kagan.board", {
    treeDataProvider: boardProvider,
    showCollapseAll: true,
  });

  const sessionsView = vscode.window.createTreeView("kagan.agents", {
    treeDataProvider: sessionsProvider,
    showCollapseAll: false,
  });

  const diffRegistration = vscode.workspace.registerTextDocumentContentProvider(
    "kagan-diff",
    diffProvider,
  );
  const reviewRegistration = vscode.workspace.registerTextDocumentContentProvider(
    "kagan-review",
    reviewDocumentProvider,
  );

  const openInstallDocsCommand = vscode.commands.registerCommand("kagan.openInstallDocs", () => {
    void vscode.env.openExternal(
      vscode.Uri.parse("https://docs.kagan.sh/guides/vscode-extension/"),
    );
  });

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
  registerAnalyticsCommands(context, client);
  registerIntegrationCommands(context, client, boardProvider);
  registerChatParticipant(context, client, sse);

  // Mention providers
  const mentionCompletionProvider = new MentionCompletionProvider(client);
  const mentionLinkProvider = new MentionLinkProvider(client);
  const MENTION_DOCUMENT_SELECTORS: vscode.DocumentSelector = [
    { language: "plaintext" },
    { language: "markdown" },
  ];

  context.subscriptions.push(
    vscode.languages.registerCompletionItemProvider(
      MENTION_DOCUMENT_SELECTORS,
      mentionCompletionProvider,
      "#",
    ),
    vscode.languages.registerDocumentLinkProvider(
      MENTION_DOCUMENT_SELECTORS,
      mentionLinkProvider,
    ),
  );

  // Polling fallback: refresh board when SSE is disconnected
  sse.setPollingFallback(() => {
    void refreshBoard(client, boardProvider, statusBar);
  });

  const messageSubscription = sse.onMessage((message: SSEMessage) => {
    boardProvider.onSSE(message);
    outputProvider.onSSE(message);

    if (message.type === SSE_TYPE.TASK_UPDATED) {
      void refreshCounts(client, statusBar);
      sessionsProvider.refresh();
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

    const { serverUrl: nextUrl, protocol: nextProtocol, authToken: nextToken } = readConnectionConfig();

    client.setBaseUrl(nextUrl);
    client.setProtocol(nextProtocol);
    client.setToken(nextToken || undefined);

    const wasStarted = sse.isStarted();
    sse.stop();
    if (wasStarted) {
      sse.start();
    }
  });

  context.subscriptions.push(
    boardView,
    sessionsView,
    sessionsProvider,
    diffRegistration,
    reviewRegistration,
    openInstallDocsCommand,
    connectCommand,
    disconnectCommand,
    refreshCommand,
    messageSubscription,
    connectedSubscription,
    configSubscription,
    sse,
    scmProvider,
    outputProvider,
    reviewDocumentProvider,
    reviewProvider,
    statusBar,
    serverLog,
    serverSupervisor,
  );

  statusBar.showDisconnected();
  void vscode.commands.executeCommand("setContext", "kagan.connected", false);

  // Preflight runs first so its showReady/Degraded/SetupNeeded cannot clobber
  // the task-count display that connect() writes via showConnected().
  void (async () => {
    await doctorStatus.runPreflight();

    const hasKaganContext = await workspaceHasKaganContext();
    if (
      hasKaganContext &&
      vscode.workspace.getConfiguration("kagan").get<boolean>("autoConnect", true)
    ) {
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
  })();

  function getServerLaunchSettings(): { autoStartServer: boolean; serverCommand: string } {
    const nextConfig = vscode.workspace.getConfiguration("kagan");
    return {
      autoStartServer: nextConfig.get<boolean>("autoStartServer", true),
      serverCommand: nextConfig.get<string>("serverCommand", "kagan").trim() || "kagan",
    };
  }
}

export async function deactivate(): Promise<void> {
  await activeServerSupervisor?.stop();
  activeServerSupervisor = null;
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

async function workspaceHasKaganContext(): Promise<boolean> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) return false;

  for (const folder of folders) {
    try {
      await vscode.workspace.fs.stat(vscode.Uri.joinPath(folder.uri, ".kagan"));
      return true;
    } catch {
      // Keep checking remaining workspace folders.
    }
  }

  return false;
}
