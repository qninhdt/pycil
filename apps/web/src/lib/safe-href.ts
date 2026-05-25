/**
 * URL allowlist for user-supplied href values (notification payloads, etc).
 *
 * Returns the URL when safe, otherwise null — caller renders a `<span>` instead
 * of an `<a>`. Same protocol-relative protections as `safeCallbackUrl` for OAuth.
 */
const ABS = /^https?:\/\//i;

export function safeHref(input?: string | null): string | null {
  if (!input) return null;
  if (ABS.test(input)) return input;
  if (!input.startsWith("/")) return null;
  if (input.startsWith("//") || input.startsWith("/\\")) return null;
  return input;
}

export function safeCallbackUrl(input: string | undefined): string {
  if (!input) return "/dashboard";
  if (!input.startsWith("/")) return "/dashboard";
  if (input.startsWith("//") || input.startsWith("/\\")) return "/dashboard";
  return input;
}
