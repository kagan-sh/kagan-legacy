import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// vscode must be mocked before importing any module that imports it.
// vi.mock is hoisted — factory cannot reference outer-scope variables.
vi.mock("vscode", () => {
  const ThemeColor = class {
    constructor(public readonly id: string) {}
  };

  const statusBarItem = {
    text: "",
    tooltip: undefined as string | undefined,
    backgroundColor: undefined as unknown,
    command: undefined as string | undefined,
    show: vi.fn(),
    hide: vi.fn(),
    dispose: vi.fn(),
  };

  const terminal = {
    show: vi.fn(),
    sendText: vi.fn(),
  };

  return {
    window: {
      createStatusBarItem: vi.fn(() => statusBarItem),
      showWarningMessage: vi.fn(),
      createTerminal: vi.fn(() => terminal),
    },
    workspace: {
      getConfiguration: vi.fn(() => ({
        get: (_key: string, def: unknown) => def,
      })),
    },
    env: {
      openExternal: vi.fn(),
    },
    StatusBarAlignment: { Left: 1 },
    ThemeColor,
    Uri: {
      parse: (s: string) => ({ toString: () => s }),
    },
  };
});

import * as vscode from "vscode";
import { DoctorStatusProvider } from "./doctor.status.js";
import { StatusBar } from "../status/bar.js";
import type { KaganClient } from "../api/client.js";
import type { DoctorReportResponse } from "@kagan/shared-api-client";

function makeReport(overrides: Partial<DoctorReportResponse> = {}): DoctorReportResponse {
  return {
    checks: [],
    ok: true,
    fail_count: 0,
    warn_count: 0,
    ...overrides,
  };
}

function makeClient(report?: DoctorReportResponse | null): Pick<KaganClient, "getDoctor"> {
  if (report === null) {
    return { getDoctor: vi.fn().mockRejectedValue(new Error("ECONNREFUSED")) };
  }
  return { getDoctor: vi.fn().mockResolvedValue(report ?? makeReport()) };
}

describe("DoctorStatusProvider", () => {
  let statusBar: StatusBar;

  beforeEach(() => {
    vi.clearAllMocks();
    statusBar = new StatusBar();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows ready when all checks pass", async () => {
    const client = makeClient(makeReport({ ok: true, fail_count: 0, warn_count: 0 }));
    const provider = new DoctorStatusProvider(client as unknown as KaganClient, statusBar);

    await provider.runPreflight();

    const item = (vscode.window.createStatusBarItem as ReturnType<typeof vi.fn>).mock.results[0]
      .value as { text: string };
    expect(item.text).toBe("$(check) ᘚᘛ kagan: ready");
    expect(vscode.window.showWarningMessage).not.toHaveBeenCalled();
  });

  it("shows degraded and no notification on WARN", async () => {
    const client = makeClient(makeReport({ ok: true, fail_count: 0, warn_count: 2 }));
    const provider = new DoctorStatusProvider(client as unknown as KaganClient, statusBar);

    await provider.runPreflight();

    const item = (vscode.window.createStatusBarItem as ReturnType<typeof vi.fn>).mock.results[0]
      .value as { text: string };
    expect(item.text).toBe("$(alert) ᘚᘛ kagan: degraded");
    expect(vscode.window.showWarningMessage).not.toHaveBeenCalled();
  });

  it("shows setup needed and fires notification on FAIL", async () => {
    vi.mocked(vscode.window.showWarningMessage).mockResolvedValue(undefined as never);

    const client = makeClient(makeReport({ ok: false, fail_count: 1, warn_count: 0 }));
    const provider = new DoctorStatusProvider(client as unknown as KaganClient, statusBar);

    await provider.runPreflight();

    const item = (vscode.window.createStatusBarItem as ReturnType<typeof vi.fn>).mock.results[0]
      .value as { text: string };
    expect(item.text).toBe("$(warning) ᘚᘛ kagan: setup needed");
    await vi.waitFor(() =>
      expect(vscode.window.showWarningMessage).toHaveBeenCalledWith(
        "Kagan: setup needed — one or more required checks failed.",
        "Open TUI",
        "Open Web",
      ),
    );
  });

  it("does not show notification on WARN (only on FAIL)", async () => {
    const client = makeClient(makeReport({ ok: true, fail_count: 0, warn_count: 3 }));
    const provider = new DoctorStatusProvider(client as unknown as KaganClient, statusBar);

    await provider.runPreflight();

    expect(vscode.window.showWarningMessage).not.toHaveBeenCalled();
  });

  it("opens a terminal with 'kagan tui' when Open TUI is chosen", async () => {
    vi.mocked(vscode.window.showWarningMessage).mockResolvedValue("Open TUI" as never);

    const client = makeClient(makeReport({ ok: false, fail_count: 1, warn_count: 0 }));
    const provider = new DoctorStatusProvider(client as unknown as KaganClient, statusBar);

    await provider.runPreflight();
    await vi.waitFor(() => expect(vscode.window.createTerminal).toHaveBeenCalled());

    expect(vscode.window.createTerminal).toHaveBeenCalledWith({ name: "Kagan TUI" });
    const terminal = vi.mocked(vscode.window.createTerminal).mock.results[0].value as {
      show: () => void;
      sendText: (text: string, addNewLine: boolean) => void;
    };
    expect(terminal.show).toHaveBeenCalled();
    expect(terminal.sendText).toHaveBeenCalledWith("kagan tui", true);
  });

  it("calls openExternal when Open Web is chosen", async () => {
    vi.mocked(vscode.window.showWarningMessage).mockResolvedValue("Open Web" as never);

    const client = makeClient(makeReport({ ok: false, fail_count: 1, warn_count: 0 }));
    const provider = new DoctorStatusProvider(client as unknown as KaganClient, statusBar);

    await provider.runPreflight();
    await vi.waitFor(() => expect(vscode.env.openExternal).toHaveBeenCalled());

    const calledWith = vi.mocked(vscode.env.openExternal).mock.calls[0][0] as {
      toString(): string;
    };
    expect(calledWith.toString()).toBe("http://localhost:8765");
  });

  it("silently stays offline when server is unreachable", async () => {
    const client = makeClient(null);
    const provider = new DoctorStatusProvider(client as unknown as KaganClient, statusBar);

    // Must not throw and must not show a notification.
    await expect(provider.runPreflight()).resolves.toBeUndefined();
    expect(vscode.window.showWarningMessage).not.toHaveBeenCalled();
  });
});
