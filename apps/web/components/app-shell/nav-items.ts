import {
  Bot,
  GraduationCap,
  LayoutDashboard,
  Library,
  Search,
  Settings,
} from "lucide-react";

export interface NavItem {
  title: string;
  href: string;
  icon: typeof LayoutDashboard;
}

export const navItems: NavItem[] = [
  { title: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { title: "Library", href: "/library", icon: Library },
  { title: "Study", href: "/study", icon: GraduationCap },
  { title: "Assistant", href: "/assistant", icon: Bot },
  { title: "Settings", href: "/settings", icon: Settings },
];
