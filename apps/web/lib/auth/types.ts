export interface SessionUser {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  tokenVersion?: number;
}

export interface SessionData {
  accessToken?: string;
  refreshToken?: string;
  expiresAt?: number;       // Unix timestamp in seconds
  refreshExpiresAt?: number;
  user?: SessionUser;
  isLoggedIn: boolean;
}
