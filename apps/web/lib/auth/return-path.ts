import "server-only";

/**
 * Where to send someone after sign-in, carried across the OAuth round trip.
 *
 * The provider round trip cannot carry it: `state` is minted and verified by the
 * API, so the app has nowhere to put its own value in the redirect chain. A
 * short-lived cookie set before leaving and read on return is the only place it
 * survives, and it is scoped to the callback path so it is sent nowhere else.
 */
export const RETURN_PATH_COOKIE = "pycil_return_path";

/** Two minutes: long enough for a sign-in, short enough not to linger. */
export const RETURN_PATH_MAX_AGE = 120;

/**
 * Whether a value is safe to redirect to.
 *
 * The path arrives from a query string, so an attacker chooses it. Anything but
 * a single-slash-prefixed relative path is refused: `//evil.example` is a
 * protocol-relative URL that most parsers treat as another origin, and a
 * backslash is normalised to a slash by some browsers, so both are open
 * redirects that would send someone off-site from a link that looks internal.
 */
export function isSafeReturnPath(value: string | null | undefined): value is string {
  if (!value) return false;
  if (!value.startsWith("/")) return false;
  if (value.startsWith("//") || value.startsWith("/\\")) return false;
  return true;
}

/** The path to land on, or `/` when there is nothing safe to use. */
export function resolveReturnPath(value: string | null | undefined): string {
  return isSafeReturnPath(value) ? value : "/";
}
