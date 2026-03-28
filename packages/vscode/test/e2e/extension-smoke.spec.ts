describe("Kagan VS Code extension", () => {
  it("opens diff and review documents against the dummy Kagan server", async () => {
    await browser.executeWorkbench(async (vscode) => {
      await vscode.commands.executeCommand("kagan.connect");
    });

    await browser.executeWorkbench(async (vscode) => {
      await vscode.commands.executeCommand("kagan.task.diff", {
        kind: "task",
        task: {
          id: "task-1",
          title: "Review extension diff",
        },
      });
    });

    await browser.waitUntil(async () => {
      const scheme = await browser.executeWorkbench((vscode) => {
        return vscode.window.activeTextEditor?.document.uri.scheme ?? "";
      });
      return scheme === "kagan-diff";
    });

    const diffText = await browser.executeWorkbench((vscode) => {
      return vscode.window.activeTextEditor?.document.getText() ?? "";
    });
    await expect(diffText).toContain("diff --git a/README.md b/README.md");

    await browser.executeWorkbench(async (vscode) => {
      await vscode.commands.executeCommand("kagan.task.open", {
        kind: "task",
        task: {
          id: "task-1",
          title: "Review extension diff",
        },
      });
    });

    await browser.waitUntil(async () => {
      const scheme = await browser.executeWorkbench((vscode) => {
        return vscode.window.activeTextEditor?.document.uri.scheme ?? "";
      });
      return scheme === "kagan-review";
    });

    const reviewText = await browser.executeWorkbench((vscode) => {
      return vscode.window.activeTextEditor?.document.getText() ?? "";
    });
    await expect(reviewText).toContain("## Verdict Summary");
  });
});
