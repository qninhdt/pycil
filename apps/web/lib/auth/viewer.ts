import "server-only";

import type { SessionData } from "./types";

/**
 * Everything the browser is allowed to know about the signed-in person.
 *
 * `SessionData` also holds `accessToken` and `refreshToken`. Handing that object
 * to a client component serialises both into the RSC Flight payload in
 * plaintext, where any script on the page can read them. This projection exists
 * so the boundary is a type error rather than a review comment: client
 * components accept `ViewerSummary`, never `SessionData`.
 */
export interface ViewerSummary {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
}

export function toViewerSummary(session: SessionData): ViewerSummary | null {
  if (!session.isLoggedIn || !session.user) return null;
  const { id, email, name, image } = session.user;
  return { id, email, name, image };
}
