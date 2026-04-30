/**
 * tasks.test.ts — unit tests for pickGithubIssue prompt branching.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

// showQuickPick and showInputBox are set up before importing the module
const showQuickPick = vi.fn();
const showInputBox = vi.fn();

vi.mock("vscode", () => ({
  window: {
    showQuickPick: (...args: unknown[]) => showQuickPick(...args),
    showInputBox: (...args: unknown[]) => showInputBox(...args),
    showErrorMessage: vi.fn(),
    showWarningMessage: vi.fn(),
  },
}));

// Mock KaganClient
const detectGithubRepo = vi.fn();

const client = {
  detectGithubRepo,
} as unknown as import("../api/client.js").KaganClient;

import { pickGithubIssue } from "./tasks.js";

describe("pickGithubIssue", () => {
  beforeEach(() => {
    detectGithubRepo.mockReset();
    showQuickPick.mockReset();
    showInputBox.mockReset();
  });

  it("returns cancelled=false, value=undefined when no GitHub repo detected", async () => {
    detectGithubRepo.mockResolvedValue({ repo_slug: null });
    const result = await pickGithubIssue(client);
    expect(result.cancelled).toBe(false);
    expect(result.value).toBeUndefined();
    expect(showQuickPick).not.toHaveBeenCalled();
  });

  it("returns cancelled=false, value=undefined when GitHub unavailable", async () => {
    detectGithubRepo.mockRejectedValue(new Error("unavailable"));
    const result = await pickGithubIssue(client);
    expect(result.cancelled).toBe(false);
    expect(result.value).toBeUndefined();
  });

  it("returns cancelled=true when user dismisses the quick pick", async () => {
    detectGithubRepo.mockResolvedValue({ repo_slug: "owner/repo" });
    showQuickPick.mockResolvedValue(undefined); // user dismissed

    const result = await pickGithubIssue(client);
    expect(result.cancelled).toBe(true);
  });

  it('returns value=undefined for "None" selection', async () => {
    detectGithubRepo.mockResolvedValue({ repo_slug: "owner/repo" });
    showQuickPick.mockResolvedValue({ label: "None", value: undefined });

    const result = await pickGithubIssue(client);
    expect(result.cancelled).toBe(false);
    expect(result.value).toBeUndefined();
  });

  it('returns value="new" for "Create new issue" selection', async () => {
    detectGithubRepo.mockResolvedValue({ repo_slug: "owner/repo" });
    showQuickPick.mockResolvedValue({ label: "Create new issue from task", value: "new" });

    const result = await pickGithubIssue(client);
    expect(result.cancelled).toBe(false);
    expect(result.value).toBe("new");
  });

  it('prompts for number and returns it for "Link" selection', async () => {
    detectGithubRepo.mockResolvedValue({ repo_slug: "owner/repo" });
    showQuickPick.mockResolvedValue({ label: "Link to existing issue (#N)", value: "__link__" });
    showInputBox.mockResolvedValue("42");

    const result = await pickGithubIssue(client);
    expect(result.cancelled).toBe(false);
    expect(result.value).toBe("42");
  });

  it('strips leading # from number input', async () => {
    detectGithubRepo.mockResolvedValue({ repo_slug: "owner/repo" });
    showQuickPick.mockResolvedValue({ label: "Link to existing issue (#N)", value: "__link__" });
    showInputBox.mockResolvedValue("#99");

    const result = await pickGithubIssue(client);
    expect(result.value).toBe("99");
  });

  it("returns cancelled=true when user dismisses number input", async () => {
    detectGithubRepo.mockResolvedValue({ repo_slug: "owner/repo" });
    showQuickPick.mockResolvedValue({ label: "Link to existing issue (#N)", value: "__link__" });
    showInputBox.mockResolvedValue(undefined); // user dismissed

    const result = await pickGithubIssue(client);
    expect(result.cancelled).toBe(true);
  });
});
