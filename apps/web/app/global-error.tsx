"use client"

/**
 * The last resort: this replaces the root layout, so it renders its own `<html>`
 * and `<body>` and cannot use anything the layout provides — no fonts, no theme
 * class, no providers. Reaching it means the root layout itself failed.
 *
 * That is why the styling here is inline rather than Tailwind: a failure this
 * high up may well be the stylesheet not loading, and a screen that says nothing
 * is worse than an unstyled one that does.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100dvh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1.5rem",
          background: "#FBFAF8",
          color: "#191817",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        <main style={{ maxWidth: "32rem" }}>
          <h1 style={{ fontSize: "1.25rem", margin: "0 0 0.5rem" }}>
            Pycil could not start
          </h1>
          <p style={{ margin: "0 0 1rem", lineHeight: 1.6 }}>
            Something failed before the app could render. Reloading is the first
            thing to try.
          </p>
          {error.digest ? (
            <p
              style={{
                margin: "0 0 1rem",
                fontFamily: "ui-monospace, monospace",
                fontSize: "0.75rem",
              }}
            >
              Reference: {error.digest}
            </p>
          ) : null}
          <button
            type="button"
            onClick={reset}
            style={{
              minHeight: "2.75rem",
              padding: "0 1rem",
              border: "1px solid #E4E1DC",
              borderRadius: "8px",
              background: "#FFFFFF",
              color: "inherit",
              font: "inherit",
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  )
}
