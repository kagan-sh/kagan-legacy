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
              group: ["**/api/generated-wire-types", "**/api/generated-wire-types.ts"],
              message:
                "Import wire types from @/lib/api/types or @kagan/shared-api-client. The generated-wire-types file has been deleted — extend scripts/generate_wire_types.py instead.",
            },
          ],
        },
      ],
    },
  },
];

export default config;
