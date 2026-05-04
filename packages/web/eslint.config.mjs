// @ts-check
/**
 * ESLint configuration for packages/web.
 *
 * Key rule: no-restricted-imports blocks direct imports from hand-rolled
 * type files. All wire types must come from @kagan/shared-api-client (or
 * the thin re-export shim at @/lib/api/types).
 */

/** @type {import("eslint").Linter.Config[]} */
const config = [
  {
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              // Block both the deleted generated file and any future
              // hand-rolled `api/types*.ts` siblings (types2.ts, types_v2.ts,
              // etc.). The shim at `@/lib/api/types` is exempt because it
              // re-exports from @kagan/shared-api-client. (Greptile P2.)
              group: [
                "**/api/generated-wire-types",
                "**/api/generated-wire-types.ts",
                "**/api/types[0-9]*",
                "**/api/types_*",
                "**/api/types-*",
              ],
              message:
                "Import wire types from @/lib/api/types or @kagan/shared-api-client. Hand-rolled api/types*.ts files are forbidden — extend scripts/generate_wire_types.py instead.",
            },
          ],
        },
      ],
    },
  },
];

export default config;
