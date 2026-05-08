import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  ThemeIcon: vi.fn(function ThemeIcon(this: { id: string }, id: string) {
    this.id = id;
  }),
  TreeItem: vi.fn(function TreeItem(
    this: { label: string; collapsibleState: number },
    label: string,
    collapsibleState: number,
  ) {
    this.label = label;
    this.collapsibleState = collapsibleState;
  }),
}));

vi.mock("vscode", () => ({
  EventEmitter: vi.fn(function EventEmitter(
    this: { event: unknown; fire: () => void; dispose: () => void },
  ) {
    this.event = vi.fn();
    this.fire = vi.fn();
    this.dispose = vi.fn();
  }),
  ThemeIcon: mocks.ThemeIcon,
  TreeItem: mocks.TreeItem,
  TreeItemCollapsibleState: {
    None: 0,
  },
}));

import { SessionsTreeProvider } from "./sessions.tree.js";
import type { SessionItemResponse } from "@kagan/shared-api-client";

type CommandContribution = {
  command: string;
  when?: string;
};

type PackageManifest = {
  contributes: {
    commands: CommandContribution[];
    menus: Record<string, CommandContribution[] | undefined>;
  };
};

const manifest = JSON.parse(readFileSync("package.json", "utf8")) as PackageManifest;

function makeSession(overrides: Partial<SessionItemResponse> = {}): SessionItemResponse {
  return {
    id: "11110000-2222-3333-4444-555555555555",
    type: "orchestrator",
    role: null,
    status: "RUNNING",
    title: "Test Session",
    backend: "claude-code",
    project_id: null,
    task_id: null,
    session_id: null,
    chat_session_id: null,
    updated_at: "2026-05-08T10:00:00Z",
    capabilities: {
      can_chat: true,
      can_stream: true,
      can_replay: true,
      can_stop: true,
      can_close: true,
      has_kagan_tools: true,
    },
    ...overrides,
  };
}

describe("SessionsTreeProvider", () => {
  it("shows empty header when no sessions", () => {
    const provider = new SessionsTreeProvider({
      getSessions: vi.fn().mockResolvedValue({ sessions: [] }),
    } as never);

    const children = provider.getChildren();
    expect(children).toEqual([{ kind: "header", label: "No sessions" }]);
    provider.dispose();
  });

  it("renders orchestrator row", () => {
    const provider = new SessionsTreeProvider({
      getSessions: vi.fn(),
    } as never);

    const item = provider.getTreeItem({
      kind: "session",
      session: makeSession({ type: "orchestrator", title: "Orchestrator" }),
    });

    expect(item.label).toBe("◆ Orchestrator");
    expect(item.description).toBe("RUNNING");
    expect(item.iconPath).toEqual({ id: "dashboard" });
    expect(item.command).toEqual({
      command: "kagan.switchSession",
      title: "Switch to Session",
      arguments: ["11110000-2222-3333-4444-555555555555"],
    });
    provider.dispose();
  });

  it("renders general row with backend", () => {
    const provider = new SessionsTreeProvider({
      getSessions: vi.fn(),
    } as never);

    const item = provider.getTreeItem({
      kind: "session",
      session: makeSession({ type: "general", title: "General", backend: "gpt-4" }),
    });

    expect(item.label).toBe("◇ General");
    expect(item.description).toBe("gpt-4 · RUNNING");
    expect(item.iconPath).toEqual({ id: "comment" });
    provider.dispose();
  });

  it("renders task worker row", () => {
    const provider = new SessionsTreeProvider({
      getSessions: vi.fn(),
    } as never);

    const item = provider.getTreeItem({
      kind: "session",
      session: makeSession({ type: "task", role: "worker", title: "Fix bug" }),
    });

    expect(item.label).toBe("▶ Fix bug");
    expect(item.description).toBe("worker · RUNNING");
    expect(item.iconPath).toEqual({ id: "play" });
    provider.dispose();
  });

  it("renders task reviewer row", () => {
    const provider = new SessionsTreeProvider({
      getSessions: vi.fn(),
    } as never);

    const item = provider.getTreeItem({
      kind: "session",
      session: makeSession({ type: "task", role: "reviewer", title: "Review PR" }),
    });

    expect(item.label).toBe("◈ Review PR");
    expect(item.description).toBe("reviewer · RUNNING");
    expect(item.iconPath).toEqual({ id: "eye" });
    provider.dispose();
  });

  it("encodes capabilities in contextValue", () => {
    const provider = new SessionsTreeProvider({
      getSessions: vi.fn(),
    } as never);

    const canStopClose = provider.getTreeItem({
      kind: "session",
      session: makeSession({
        capabilities: {
          can_chat: true,
          can_stream: true,
          can_replay: true,
          can_stop: true,
          can_close: true,
          has_kagan_tools: true,
        },
      }),
    });
    expect(canStopClose.contextValue).toBe("session.orchestrator.none.stop_1.close_1");

    const cannotClose = provider.getTreeItem({
      kind: "session",
      session: makeSession({
        type: "task",
        role: "worker",
        capabilities: {
          can_chat: false,
          can_stream: true,
          can_replay: true,
          can_stop: true,
          can_close: false,
          has_kagan_tools: false,
        },
      }),
    });
    expect(cannotClose.contextValue).toBe("session.task.worker.stop_1.close_0");

    provider.dispose();
  });
});

describe("session command exposure", () => {
  it("exposes switch, stop, close, and new general session in palette", () => {
    const commands = manifest.contributes.commands.map((c) => c.command);
    expect(commands).toContain("kagan.switchSession");
    expect(commands).toContain("kagan.stopSession");
    expect(commands).toContain("kagan.closeSession");
    expect(commands).toContain("kagan.newGeneralSession");
  });

  it("shows stop and close in context menu for capable sessions", () => {
    const items = manifest.contributes.menus["view/item/context"] ?? [];
    const stopItem = items.find((i) => i.command === "kagan.stopSession");
    const closeItem = items.find((i) => i.command === "kagan.closeSession");

    expect(stopItem?.when).toContain("stop_1");
    expect(closeItem?.when).toContain("close_1");
  });
});
