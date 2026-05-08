// Integration tests for the /attach and /detach chat participant commands.
//
// These tests run inside the Extension Development Host via @vscode/test-cli.
// VS Code exposes participant registration here, but not a stable API to drive
// chat requests directly. Behavior-level attach parsing/resolution is covered by
// the unit helper specs; this suite only verifies activation contributes the
// commands that other VS Code surfaces call.

import * as assert from "node:assert/strict";
import { after, before, suite, test } from "mocha";
import * as vscode from "vscode";
import {
  TEST_SERVER_URL,
  createFakeKaganServer,
} from "../helpers/fake-kagan-server.js";

suite("Chat participant: /attach and /detach", () => {
  const baseServer = createFakeKaganServer();

  before(async () => {
    await baseServer.start();

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
    await baseServer.stop();
  });

  test("kagan.attachToSession command is registered after activation", async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(
      commands.includes("kagan.attachToSession"),
      "expected kagan.attachToSession to be registered",
    );
  });

  test("kagan.detachFromSession command is registered after activation", async () => {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(
      commands.includes("kagan.detachFromSession"),
      "expected kagan.detachFromSession to be registered",
    );
  });
});
