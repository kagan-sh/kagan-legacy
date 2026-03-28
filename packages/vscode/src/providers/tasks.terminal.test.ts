import { describe, expect, it } from "vitest";
import { buildEditorLink, normalizeLauncher } from "./tasks.terminal.helpers.js";

describe("tasks.terminal helpers", () => {
  it("normalizes known launchers explicitly", () => {
    expect(normalizeLauncher(" Cursor ")).toBe("cursor");
    expect(normalizeLauncher("tmux")).toBe("tmux");
  });

  it("falls back to vscode for unknown launchers", () => {
    expect(normalizeLauncher("something-custom")).toBe("vscode");
  });

  it("builds deep links for POSIX paths", () => {
    expect(buildEditorLink("vscode", "/tmp/kagan repo")).toBe(
      "vscode://file/tmp/kagan%20repo",
    );
  });

  it("builds deep links for Windows paths", () => {
    expect(buildEditorLink("cursor", "C:\\Users\\alice\\repo")).toBe(
      "cursor://file/C:/Users/alice/repo",
    );
  });
});
