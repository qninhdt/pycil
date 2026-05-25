import type { UUID } from "./node";

export interface CurrentUser {
  id: UUID;
  email: string;
  name: string | null;
  image: string | null;
}
