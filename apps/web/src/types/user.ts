export interface User {
  id: string;
  name: string;
  username: string;
  email: string;
  avatar: string;
  coverImage: string;
  followers: number;
  following: number;
  level: number;
  streak: number;
  coins: number;
  badges: Badge[];
  referralCoins: number;
  referralLink: string;
}

export interface Badge {
  id: string;
  name: string;
  icon: string;
  description: string;
}
