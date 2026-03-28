import * as assert from "node:assert/strict";
import { after, before, setup, suite, teardown, test } from "mocha";
import * as vscode from "vscode";
import {
  TEST_SERVER_URL,
  TEST_TASK,
  createFakeKaganServer,
} from "../helpers/fake-kagan-server.js";

suite("Kagan Extension", () => {
  const server = createFakeKaganServer();

  setup(async () => {
    await closeAllEditors();
  });

  teardown(async () => {
    await closeAllEditors();
  });

  before(async () => {
    await server.start();

    const extension = vscode.extensions.getExtension("kagan.kagan-vscode");
    assert.ok(extension, "expected the Kagan extension to be installed");

    await vscode.workspace
      .getConfiguration("kagan")
      .update("serverUrl", TEST_SERVER_URL, vscode.ConfigurationTarget.Workspace);
    await vscode.workspace
      .getConfiguration("kagan")
      .update("autoConnect", false, vscode.ConfigurationTarget.Workspace);

    await extension.activate();
  });

  after(async () => {
    await server.stop();
  });

  test("registers the public commands", async () => {
    const commands = await vscode.commands.getCommands(true);

    assert.ok(commands.includes("kagan.connect"));
    assert.ok(commands.includes("kagan.task.diff"));
    assert.ok(commands.includes("kagan.task.open"));
  });

  test("opens a diff document for a task", async () => {
    await vscode.commands.executeCommand("kagan.connect");
    await vscode.commands.executeCommand("kagan.task.diff", { kind: "task", task: TEST_TASK });

    const editor = await waitForActiveEditor("kagan-diff");
    assert.ok(editor);
    assert.match(editor.document.getText(), /diff --git a\/README\.md b\/README\.md/);
  });

  test("opens a review document for a task", async () => {
    await vscode.commands.executeCommand("kagan.task.open", { kind: "task", task: TEST_TASK });

    const editor = await waitForActiveEditor("kagan-review");
    assert.ok(editor);
    assert.match(editor.document.getText(), /## Verdict Summary/);
    assert.match(editor.document.getText(), /FAIL: Review still needs a human check\./);
  });
});

async function waitForActiveEditor(
  scheme: string,
  timeoutMs: number = 5000,
): Promise<vscode.TextEditor> {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const editor = vscode.window.activeTextEditor;
    if (editor?.document.uri.scheme === scheme) {
      return editor;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }

  throw new Error(`Timed out waiting for active editor with scheme ${scheme}`);
}

async function closeAllEditors(): Promise<void> {
  await vscode.commands.executeCommand("workbench.action.closeAllEditors");
}
