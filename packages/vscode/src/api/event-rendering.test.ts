import { describe, expect, it } from "vitest";
import { renderEvent } from "./event-rendering";

describe("renderEvent / CRITERION_VERDICT", () => {
  it("PASS → label PASS, severity success", () => {
    const result = renderEvent("CRITERION_VERDICT", { verdict: "PASS", reason: "all good" });
    expect(result).not.toBeNull();
    expect(result!.title).toBe("PASS");
    expect(result!.severity).toBe("success");
    expect(result!.body).toBe("all good");
  });

  it("SKIP → label SKIP, severity info", () => {
    const result = renderEvent("CRITERION_VERDICT", { verdict: "SKIP", reason: "not tested" });
    expect(result).not.toBeNull();
    expect(result!.title).toBe("SKIP");
    expect(result!.severity).toBe("info");
    expect(result!.body).toBe("not tested");
  });

  it("FAIL → label FAIL, severity warning", () => {
    const result = renderEvent("CRITERION_VERDICT", { verdict: "FAIL", reason: "broke" });
    expect(result).not.toBeNull();
    expect(result!.title).toBe("FAIL");
    expect(result!.severity).toBe("warning");
    expect(result!.body).toBe("broke");
  });

  it("unknown verdict falls back to FAIL / warning", () => {
    const result = renderEvent("CRITERION_VERDICT", { verdict: "UNKNOWN", reason: "" });
    expect(result).not.toBeNull();
    expect(result!.title).toBe("FAIL");
    expect(result!.severity).toBe("warning");
  });

  it("metadata carries raw verdict string", () => {
    const result = renderEvent("CRITERION_VERDICT", { verdict: "SKIP", reason: "skipped" });
    expect(result!.metadata).toMatchObject({ verdict: "SKIP", reason: "skipped" });
  });
});
