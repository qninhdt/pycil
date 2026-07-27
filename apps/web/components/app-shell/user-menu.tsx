"use client";

import React, { useState } from "react";
import { LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { SessionUser } from "@/lib/auth/types";

export function UserMenu({ user }: { user?: SessionUser }) {
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  if (!user) return null;

  const initials = user.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : user.email.slice(0, 2).toUpperCase();

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch (err) {
      console.error("Logout error:", err);
    } finally {
      window.location.href = "/login";
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        type="button"
        className="flex items-center gap-2 rounded-xl p-1 text-left text-sm transition-all hover:bg-accent outline-none cursor-pointer border border-transparent hover:border-border"
      >
        <Avatar size="sm" className="ring-2 ring-primary/20 shrink-0">
          {user.image && <AvatarImage src={user.image} alt={user.name || user.email} />}
          <AvatarFallback className="font-semibold bg-primary/10 text-primary">
            {initials}
          </AvatarFallback>
        </Avatar>
        <div className="hidden flex-1 overflow-hidden text-left text-xs md:block">
          <div className="truncate font-semibold text-foreground">
            {user.name || "User"}
          </div>
          <div className="truncate text-muted-foreground text-[11px]">{user.email}</div>
        </div>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-56 p-2 shadow-xl border-2 z-50">
        {/* User Info Header */}
        <DropdownMenuGroup>
          <DropdownMenuLabel className="font-normal p-2">
            <div className="flex items-center gap-3">
              <Avatar className="h-9 w-9 ring-2 ring-primary/20 shrink-0">
                {user.image && <AvatarImage src={user.image} alt={user.name || user.email} />}
                <AvatarFallback className="font-bold bg-primary/15 text-primary">
                  {initials}
                </AvatarFallback>
              </Avatar>
              <div className="flex flex-col space-y-0.5 overflow-hidden text-left">
                <p className="text-sm font-bold leading-none truncate text-foreground">
                  {user.name || "User"}
                </p>
                <p className="text-xs text-muted-foreground truncate">{user.email}</p>
              </div>
            </div>
          </DropdownMenuLabel>
        </DropdownMenuGroup>

        <DropdownMenuSeparator className="my-1.5" />

        {/* Settings Item */}
        <DropdownMenuItem render={<Link href="/settings" />} className="cursor-pointer py-2">
          <Settings className="size-4 mr-2 text-muted-foreground" />
          <span className="font-medium">Settings</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator className="my-1.5" />

        {/* Logout Item */}
        <DropdownMenuItem
          variant="destructive"
          className="cursor-pointer py-2 font-semibold text-rose-600 focus:text-rose-600 focus:bg-rose-500/10 dark:text-rose-400 dark:focus:bg-rose-500/20"
          onClick={handleLogout}
          disabled={isLoggingOut}
        >
          <LogOut className="size-4 mr-2 text-rose-500" />
          <span>{isLoggingOut ? "Logging out..." : "Log out"}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
