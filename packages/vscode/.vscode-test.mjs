import { defineConfig } from "@vscode/test-cli";

export default defineConfig({
  files: ".vscode-test-build/test/integration/**/*.test.js",
  workspaceFolder: "./test/fixture-workspace",
  version: "stable",
  mocha: {
    timeout: 30000,
  },
});
