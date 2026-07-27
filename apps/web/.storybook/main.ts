import type { StorybookConfig } from "@storybook/nextjs-vite"

/**
 * Storybook is the review surface for the token layer. It exists here rather
 * than as a throwaway gallery page so a defect that only appears in a loading,
 * empty, or error state is visible before screens are built on top of it.
 */
const config: StorybookConfig = {
  stories: ["../stories/**/*.stories.@(ts|tsx)"],
  addons: ["@storybook/addon-a11y", "@storybook/addon-docs"],
  framework: {
    name: "@storybook/nextjs-vite",
    options: {},
  },
  typescript: {
    // The Next.js build is the type gate. Re-running a docgen type check here
    // doubles the build time and reports the same errors twice.
    reactDocgen: "react-docgen",
  },
}

export default config
