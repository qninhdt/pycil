# Phase 5 teardown inventory

Written before any deletion, per phase 5 step 4.

## `components.json` resolution: the plan's finding 1 is wrong

The plan required writing `"base": "base"` into `components.json` before any CLI
call, on the premise that a present config without that key falls through to
`radix`. Both halves of that are false in the installed CLI (4.13.1).

`Vf` does not receive the config object. It receives the **style string**:

```js
// dist/chunk-2XFBGS5K.js
var c = ["radix", "base", "aria"];
function k(e) {                                  // exported as c$2
  let t = e ? c.find(n => e.startsWith(`${n}-`)) : void 0;
  return { base: t, style: t ? e?.slice(t.length + 1) : e };
}
// dist/chunk-UBIN4IG2.js
function Vf(e) { return e === void 0 ? "base" : c$2(e).base ?? "radix"; }
```

So the base is encoded as a **prefix of `style`**. Replayed against the real code:

| `style` | resolved base |
|---|---|
| `base-nova` (this project) | `base` |
| `nova` | `radix` |
| `radix-nova` | `radix` |
| absent | `base` |

This project already has `"style": "base-nova"`, so it already resolves to `base`.
There was never a Radix-swap risk from the config, and the primitives on disk
confirm it: all 60 import `@base-ui/react`.

Worse, the prescribed fix breaks the tool. The config file schema is `.strict()`,
so an unknown `base` key makes the whole file invalid:

```
Invalid configuration found in /home/qninh/projects/pycil/apps/web/components.json.
```

**Applied instead:** no `base` key; `iconLibrary` set to `phosphor` (a valid
member of the CLI's icon enum `["lucide","hugeicons","tabler","phosphor","remixicon"]`).
Verified by the CLI itself rather than by reading the source:

```
$ pnpm dlx shadcn@4.13.1 info --json
    "style": "base-nova",
    "base": "base",
    "iconLibrary": "phosphor",
```

The phase's real intent — the CLI must resolve `base`, and the primitive library
must stay Base UI — is satisfied and now machine-verified. The success criterion
that literally requires the key in the file is unsatisfiable and is rewritten.

## Registry closure is already satisfied on disk

Computed from actual intra-`components/ui` imports rather than from registry
metadata:

```
alert-dialog    -> button
combobox        -> button input-group
command         -> dialog input-group
dialog          -> button
field           -> label separator
input-group     -> button input textarea
message-scroller-> button
sheet           -> button
toggle-group    -> toggle
```

Every dependency lands inside the keep set. No keep-set file imports anything in
the delete set, so the deletion is closed. `input-group`, `label` and `toggle` are
the closure additions the plan named, and all three are already present.

## Keep: 42 present + 1 to add

The `/DESIGN.md` primitive inventory (39 of its 40 names exist; `toast` does not)
plus the three closure additions.

```
accordion alert alert-dialog avatar badge breadcrumb bubble button card chart
checkbox collapsible combobox command dialog drawer dropdown-menu empty field
input input-group kbd label marker message message-scroller popover progress
radio-group scroll-area select separator sheet skeleton spinner switch table tabs
textarea toggle toggle-group tooltip
```

To add: `toast` (the only inventory entry with no file on disk).

## Delete: 18

```
aspect-ratio attachment button-group calendar carousel context-menu direction
hover-card input-otp item menubar native-select navigation-menu pagination
resizable sidebar slider sonner
```

42 + 18 = 60, matching `ls components/ui | wc -l`.

`direction` was checked separately: no file anywhere in `app/`, `components/` or
`lib/` references it or `DirectionProvider`, and `rtl` is `false`.

## Retained-layer coupling

One, exactly as the plan predicted:

- `lib/realtime/provider.tsx:5` imports `getRealtimeToken` from
  `@/lib/actions/realtime`, which this phase deletes. Recorded, not patched;
  phase 7 owns `lib/realtime/**` and recreates the action.

Grep over `lib/api`, `lib/auth`, `lib/realtime`, `proxy.ts` and `app/api` found no
other reference to `lib/query`, `lib/actions`, `lib/stores` or
`use-assistant-stream`.

## Lucide importers

21 of 60 primitives import `lucide-react`, but only **11** are in the keep set, so
the codemod is 11 files, not 21. The other 10 leave with the delete set.
