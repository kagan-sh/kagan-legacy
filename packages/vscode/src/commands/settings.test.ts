import { describe, expect, it, vi } from "vitest";

vi.mock("vscode", () => ({}));

import { describeBackendStatus, sortBackends } from "./settings.js";

describe("settings command helpers", () => {
  it("sorts reference backends first and then availability", () => {
    const sorted = sortBackends([
      { name: "cursor", available: true },
      { name: "codex", available: false, reference: true },
      { name: "claude-code", available: true, reference: true },
    ]);

    expect(sorted.map((backend) => backend.name)).toEqual(["claude-code", "codex", "cursor"]);
  });

  it("describes current, reference, and unavailable states", () => {
    expect(
      describeBackendStatus(
        { name: "claude-code", available: true, reference: true },
        "claude-code",
      ),
    ).toBe("Current · Reference");

    expect(
      describeBackendStatus(
        { name: "codex", available: false, reference: true },
        "claude-code",
      ),
    ).toBe("Reference · Unavailable");

    expect(
      describeBackendStatus(
        { name: "cursor", available: true },
        "claude-code",
      ),
    ).toBeUndefined();
  });
});
