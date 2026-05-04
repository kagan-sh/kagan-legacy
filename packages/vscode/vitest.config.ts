import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Resolve @kagan/shared-api-client straight to its source so Vitest
// doesn't depend on the workspace package's dist/ being built — CI runs
// `pnpm install --frozen-lockfile && pnpm run test:unit` and does NOT
// build the shared package's dist/ between those two commands.
const sharedSrc = fileURLToPath(new URL("../shared/api-client/src/index.ts", import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@kagan/shared-api-client": sharedSrc,
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    exclude: ["test/**/*", "dist/**/*", "node_modules/**/*"],
  },
});
