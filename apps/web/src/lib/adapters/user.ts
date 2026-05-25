import type { CurrentUser } from "@/types/domain";
import type { User } from "@/types/user";

export function currentUserToUser(u: CurrentUser): User {
  return {
    id: u.id,
    name: u.name ?? u.email,
    username: u.email.split("@")[0] ?? "",
    email: u.email,
    avatar: u.image ?? "",
    coverImage: "",
    followers: 0,
    following: 0,
    level: 0,
    streak: 0,
    coins: 0,
    badges: [],
    referralCoins: 0,
    referralLink: "",
  };
}
