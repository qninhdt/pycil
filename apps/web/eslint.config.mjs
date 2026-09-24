import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * The screen features each own one surface and coordinate through stores and
 * the shell rather than by reaching into each other's files. `components/ui`,
 * `components/vocabulary`, and `components/theme` are shared layers any feature
 * may use, and `components/shell` plus `components/command` compose screens by
 * design, so they live outside this list.
 */
const screenFeatures = [
  "activity",
  "assistant",
  "dashboard",
  "library",
  "progress",
  "settings",
  "study",
];

const screenFeatureBoundaryRules = screenFeatures.map((feature) => ({
  files: [`components/${feature}/**`],
  rules: {
    "no-restricted-imports": [
      "error",
      {
        patterns: [
          {
            group: screenFeatures
              .filter((other) => other !== feature)
              .map((other) => `@/components/${other}/**`),
            message:
              "Screen features stay independent: share through components/ui or components/vocabulary, a store, or the shell instead of importing another feature's files.",
          },
        ],
      },
    ],
  },
}));

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Tool output, for the same reason: Playwright's HTML report ships a minified
    // trace viewer, and a coverage run writes its own viewer. All are regenerated
    // by the command that produces them, so linting them is noise.
    "playwright-report/**",
    "test-results/**",
    "coverage/**",
  ]),
  {
    // Playwright names a fixture's setup callback `use`, which the React plugin
    // reads as a hook call in a non-component function. There is no React in the
    // end-to-end layer at all, so the rule can only produce false positives here;
    // renaming the parameter is not an option because the name is Playwright's
    // API, not ours.
    files: ["tests/e2e/**/*.ts"],
    rules: { "react-hooks/rules-of-hooks": "off" },
  },
  ...screenFeatureBoundaryRules,
]);

export default eslintConfig;
