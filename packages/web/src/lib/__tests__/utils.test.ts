import { describe, expect, it } from "vitest";
import { asBool, normalizeLauncher, quoteShell } from "../utils";

describe("asBool", () => {
  it("returns fallback for undefined", () => {
    expect(asBool(undefined, true)).toBe(true);
    expect(asBool(undefined, false)).toBe(false);
  });

  it("parses true values", () => {
    expect(asBool("true", false)).toBe(true);
    expect(asBool("1", false)).toBe(true);
    expect(asBool("yes", false)).toBe(true);
    expect(asBool("on", false)).toBe(true);
  });

  it("returns false for falsy strings", () => {
    expect(asBool("false", true)).toBe(false);
    expect(asBool("0", true)).toBe(false);
    expect(asBool("no", true)).toBe(false);
    expect(asBool("off", true)).toBe(false);
  });

  it("is case-insensitive and trims whitespace", () => {
    expect(asBool("FALSE", true)).toBe(false);
    expect(asBool(" False ", true)).toBe(false);
    expect(asBool("  NO  ", true)).toBe(false);
  });

  it("treats unrecognized strings as truthy", () => {
    expect(asBool("", false)).toBe(true);
    expect(asBool("anything", false)).toBe(true);
  });
});

describe("normalizeLauncher", () => {
  it("returns vscode for null/undefined/empty", () => {
    expect(normalizeLauncher(null)).toBe("vscode");
    expect(normalizeLauncher(undefined)).toBe("vscode");
    expect(normalizeLauncher("")).toBe("vscode");
  });

  it("normalizes known backends", () => {
    expect(normalizeLauncher("tmux")).toBe("tmux");
    expect(normalizeLauncher("nvim")).toBe("nvim");
    expect(normalizeLauncher("cursor")).toBe("cursor");
    expect(normalizeLauncher("windsurf")).toBe("windsurf");
    expect(normalizeLauncher("kiro")).toBe("kiro");
    expect(normalizeLauncher("antigravity")).toBe("antigravity");
  });

  it("is case-insensitive and trims whitespace", () => {
    expect(normalizeLauncher("VSCODE")).toBe("vscode");
    expect(normalizeLauncher(" Cursor ")).toBe("cursor");
  });

  it("falls back to vscode for unknown backends", () => {
    expect(normalizeLauncher("emacs")).toBe("vscode");
    expect(normalizeLauncher("sublime")).toBe("vscode");
  });
});

describe("quoteShell", () => {
  it("wraps value in double quotes", () => {
    expect(quoteShell("hello")).toBe('"hello"');
  });

  it("escapes double quotes", () => {
    expect(quoteShell('say "hi"')).toBe('"say \\"hi\\""');
  });

  it("escapes backslashes", () => {
    expect(quoteShell("path\\to")).toBe('"path\\\\to"');
  });

  it("escapes dollar signs", () => {
    expect(quoteShell("$HOME")).toBe('"\\$HOME"');
  });

  it("escapes backticks", () => {
    expect(quoteShell("`cmd`")).toBe('"\\`cmd\\`"');
  });

  it("leaves safe characters untouched", () => {
    expect(quoteShell("/usr/local/bin")).toBe('"/usr/local/bin"');
  });
});
