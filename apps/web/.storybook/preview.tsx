import * as React from "react"
import type { Decorator, Preview } from "@storybook/nextjs-vite"

import { IconWeightProvider } from "@/components/theme/icon-weight-provider"

import "../app/globals.css"
import "./preview-fonts.css"

/**
 * Applies the theme class to the story root and to `documentElement`, because
 * the token layer keys off `.dark` on an ancestor and portalled surfaces
 * (dialog, popover, toast) mount outside the story subtree. Setting only the
 * wrapper would leave every overlay rendering light tokens on a dark canvas.
 */
const withTheme: Decorator = (Story, context) => {
  const theme = context.globals.theme as "light" | "dark"

  React.useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", theme === "dark")
    return () => root.classList.remove("dark")
  }, [theme])

  return (
    <IconWeightProvider>
      <div className="bg-background text-foreground min-h-svh p-6 font-sans">
        <Story />
      </div>
    </IconWeightProvider>
  )
}

const preview: Preview = {
  decorators: [withTheme],
  initialGlobals: {
    theme: "light",
    // Viewport presets are declared through parameters. There is no
    // `@storybook/addon-viewport` package to install for this.
    viewport: { value: "mobile", isRotated: false },
  },
  globalTypes: {
    theme: {
      description: "Colour scheme",
      toolbar: {
        title: "Theme",
        icon: "circlehollow",
        items: [
          { value: "light", title: "Light" },
          { value: "dark", title: "Dark" },
        ],
        dynamicTitle: true,
      },
    },
  },
  parameters: {
    layout: "fullscreen",
    controls: { expanded: true },
    a11y: {
      // Report violations rather than failing the build: contrast is asserted
      // against /DESIGN.md by the token check, and a story is allowed to show a
      // deliberately incomplete state.
      test: "todo",
    },
    viewport: {
      options: {
        // The two widths the design spec actually specifies behaviour for.
        mobile: { name: "Mobile (390)", styles: { width: "390px", height: "844px" } },
        desktop: { name: "Desktop (1280)", styles: { width: "1280px", height: "900px" } },
      },
    },
  },
}

export default preview
