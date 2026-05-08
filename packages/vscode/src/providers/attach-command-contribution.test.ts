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

import { RunningAgentsTreeProvider } from "./running-agents.tree.js";

type CommandContribution = {
  command: string;
};

type PackageManifest = {
  contributes: {
    commands: CommandContribution[];
    menus: Record<string, CommandContribution[] | undefined>;
  };
};

const manifest = JSON.parse(readFileSync("package.json", "utf8")) as PackageManifest;

describe("attach command exposure", () => {
  it("does not expose attach-to-session through palette or context menus", () => {
    expect(manifest.contributes.commands.map((item) => item.command)).not.toContain(
      "kagan.attachToSession",
    );
    expect(manifest.contributes.menus.commandPalette?.map((item) => item.command)).not.toContain(
      "kagan.attachToSession",
    );
    expect(
      manifest.contributes.menus["view/item/context"]?.map((item) => item.command),
    ).not.toContain("kagan.attachToSession");
  });

  it("keeps running-agent tree clicks wired with an explicit session id", () => {
    const provider = new RunningAgentsTreeProvider({
      getRunningAgents: vi.fn(),
    } as never);

    const item = provider.getTreeItem({
      kind: "agent",
      agent: {
        task_id: "task-1",
        task_title: "Implement attach cleanup",
        task_status: "IN_PROGRESS",
        session_id: "session-1",
        agent_role: "worker",
        agent_backend: "claude-code",
        session_status: "RUNNING",
        started_at: "2026-05-08T10:00:00Z",
        last_event_at: "2026-05-08T10:01:00Z",
        input_tokens: 10,
        output_tokens: 20,
      },
    });

    expect(item.command).toEqual({
      command: "kagan.attachToSession",
      title: "Attach to Agent",
      arguments: ["session-1", "Implement attach cleanup"],
    });

    provider.dispose();
  });
});
