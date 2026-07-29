# Design Guidelines

The normative design source is [`/DESIGN.md`](../DESIGN.md) at the repository
root. It owns the palette, the type system, spacing, elevation, radii, and the
per-component specifications, and the token values live there and only there. A
color, a font size, or a radius is changed in `/DESIGN.md` and regenerated into
`apps/web/app/tokens.generated.css` by `pnpm --filter web tokens`; it is never
edited in a component.

This file holds the half a token table cannot carry: the mechanical rules that a
grep can enforce, so the enforceable discipline sits inside the documented `docs/`
structure while the values keep a single home.

## The ten mechanical audit rules

`apps/web/scripts/design-system-audit.mjs` (run via `pnpm --filter web
audit:design`, and in CI as part of the `test-web` job) enforces these against
every `.ts`/`.tsx` file under `app/` and `components/`. It strips comments and
string-interpolated code before matching, so a hit is a real occurrence rather
than a mention in a comment. The `components/ui/**` primitive registry is exempt
from the call-site rules, because that layer is where the tokens are wired to
Tailwind in the first place.

1. **No em dash in rendered text.** Em dashes are an editorial tell; a learner
   never reads one in the product. Comments may use them freely.
2. **No `space-y-*` / `space-x-*`.** Spacing between siblings goes through `gap`
   on a flex or grid parent, so the rhythm is owned by the container.
3. **No drop shadow** (`shadow-md`/`lg`/`xl`/`2xl`). Elevation in this system is a
   hairline ring plus the single `--shadow-hover`, never a soft drop shadow.
4. **No `h-screen`.** Full-height surfaces use `min-h-[100dvh]`; on mobile Safari
   `100vh` is taller than the visible viewport while the address bar shows, which
   pushes a submit control under the browser chrome.
5. **No raw hex colour** in TSX. Colour flows through the semantic token layer.
   The two exempt files are `app/global-error.tsx` (it renders before any
   stylesheet exists) and the `themeColor` viewport meta in `app/layout.tsx`
   (browser chrome a CSS variable cannot reach).
6. **No `dark:` colour override at a call site.** Dark-mode colour is resolved by
   the semantic tokens, not by a per-component override.
7. **No `lucide-react` import.** Icons come from `lib/icons`, which re-exports
   Phosphor at the project's chosen weight.
8. **No `w-N h-N` pair where `size-N` applies.** A square uses `size-N`.
9. **Serif reserved for lexical content.** `font-serif` (Newsreader) is allowed
   only on dictionary content — headwords, definitions, example sentences, the
   word a task or approval acts on — and on the brand wordmark. Interface chrome
   is the sans face. The audit carries the exact allow-list.
10. **Every `rounded-*` radius token is defined.** A `rounded-xs`/`-sm`/`-md`/…
    class must resolve to a `--radius-*` token declared in `app/globals.css`; an
    undefined token silently falls back to a Tailwind default, so the rendered
    corner is not the specified one.
