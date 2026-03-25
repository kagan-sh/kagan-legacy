import * as vscode from "vscode";
import { KaganClient } from "./api/client.js";
import { SSEStream } from "./api/sse.js";
import { registerReviewCommands } from "./commands/review.js";
import { registerTaskCommands } from "./commands/tasks.js";
import { BoardTreeProvider } from "./providers/board.tree.js";
import { AgentOutputProvider } from "./providers/events.output.js";
import {
  KaganDiffContentProvider,
  TaskScmProvider,
} from "./providers/tasks.scm.js";
import { ReviewCommentProvider, ReviewDocumentProvider } from "./providers/review.comments.js";
import { AgentTerminalProvider } from "./providers/tasks.terminal.js";
import { StatusBar } from "./status/bar.js";
import type { SSEMessage } from "./api/types.js";

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration("kagan");
  const client = new KaganClient(config.get<string>("serverUrl", "http://localhost:8765"));
  const sse = new SSEStream(client.getBaseUrl());
  const boardProvider = new BoardTreeProvider(client);
  const scmProvider = new TaskScmProvider(client);
  const diffProvider = new KaganDiffContentProvider(client);
  const outputProvider = new AgentOutputProvider(client);
  const reviewDocumentProvider = new ReviewDocumentProvider();
  const reviewProvider = new ReviewCommentProvider();
  const terminalProvider = new AgentTerminalProvider(client);
  const statusBar = new StatusBar();

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
    await connect(client, sse, boardProvider, statusBar);
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

  const messageSubscription = sse.onMessage((message: SSEMessage) => {
    boardProvider.onSSE(message);
    outputProvider.onSSE(message);

    if (message.type === "TASK_UPDATED") {
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
    if (!event.affectsConfiguration("kagan.serverUrl")) {
      return;
    }

    const nextUrl = vscode.workspace.getConfiguration("kagan").get<string>(
      "serverUrl",
      "http://localhost:8765",
    );
    client.setBaseUrl(nextUrl);
    sse.setBaseUrl(nextUrl);
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
  );

  statusBar.showDisconnected();
  void vscode.commands.executeCommand("setContext", "kagan.connected", false);

  if (config.get<boolean>("autoConnect", true)) {
    void connect(client, sse, boardProvider, statusBar);
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
): Promise<void> {
  statusBar.showConnecting();

  try {
    const reachable = await client.ping();
    if (!reachable) {
      throw new Error("Cannot reach Kagan server");
    }

    await client.verifyApi();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    statusBar.showError(message);
    void vscode.window.showErrorMessage(message);
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
