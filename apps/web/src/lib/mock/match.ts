// Minimal path matcher for the mock router. Supports `:param` segments and
// query strings. No new dependency.

export interface MatchResult {
  params: Record<string, string>;
  query: URLSearchParams;
}

export function matchRoute(
  pattern: string,
  path: string,
): MatchResult | null {
  const [rawPath, rawQuery = ""] = path.split("?");
  const patternSegs = pattern.split("/").filter(Boolean);
  const pathSegs = rawPath.split("/").filter(Boolean);

  if (patternSegs.length !== pathSegs.length) return null;

  const params: Record<string, string> = {};
  for (let i = 0; i < patternSegs.length; i++) {
    const p = patternSegs[i];
    const v = pathSegs[i];
    if (p.startsWith(":")) {
      params[p.slice(1)] = decodeURIComponent(v);
    } else if (p !== v) {
      return null;
    }
  }

  return { params, query: new URLSearchParams(rawQuery) };
}
