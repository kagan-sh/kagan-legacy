import * as path from "node:path";
import { createFakeKaganServer } from "./helpers/fake-kagan-server";

const server = createFakeKaganServer();

export const config = {
  runner: "local",
  specs: ["./e2e/**/*.spec.ts"],
  maxInstances: 1,
  autoCompileOpts: {
    autoCompile: true,
    tsNodeOpts: {
      project: path.join(__dirname, "tsconfig.json"),
      transpileOnly: true,
    },
  },
  capabilities: [
    {
      browserName: "vscode",
      browserVersion: "stable",
      "wdio:vscodeOptions": {
        extensionPath: path.join(__dirname, ".."),
        workspacePath: path.join(__dirname, "fixture-workspace"),
        vscodeArgs: {
          "window-size": "1400,900",
        },
      },
    },
  ],
  logLevel: "warn",
  waitforTimeout: 10000,
  connectionRetryTimeout: 120000,
  connectionRetryCount: 2,
  services: ["vscode"],
  framework: "mocha",
  reporters: ["spec"],
  mochaOpts: {
    ui: "bdd",
    timeout: 60000,
  },
  async onPrepare() {
    await server.start();
  },
  async onComplete() {
    await server.stop();
  },
};
