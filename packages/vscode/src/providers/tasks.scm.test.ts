import { describe, expect, it } from "vitest";
import { extractPatchForFile, splitDiffSections } from "./tasks.scm.helpers.js";

const DIFF = [
  "diff --git a/README.md b/README.md",
  "index 0000000..1111111 100644",
  "--- a/README.md",
  "+++ b/README.md",
  "@@ -1 +1,2 @@",
  "-Old line",
  "+Old line",
  "+New line",
  "diff --git a/src/app.ts b/src/app.ts",
  "index 2222222..3333333 100644",
  "--- a/src/app.ts",
  "+++ b/src/app.ts",
  "@@ -1 +1 @@",
  "-console.log('old')",
  "+console.log('new')",
  "",
].join("\n");

describe("tasks.scm helpers", () => {
  it("splits a unified diff into file sections", () => {
    expect(splitDiffSections(DIFF)).toHaveLength(2);
  });

  it("extracts the patch for a specific file", () => {
    const patch = extractPatchForFile(DIFF, "src/app.ts");
    expect(patch).toContain("diff --git a/src/app.ts b/src/app.ts");
    expect(patch).not.toContain("diff --git a/README.md b/README.md");
  });

  it("falls back to the whole diff when the file is missing", () => {
    expect(extractPatchForFile(DIFF, "missing.ts")).toContain(
      "diff --git a/README.md b/README.md",
    );
  });
});
