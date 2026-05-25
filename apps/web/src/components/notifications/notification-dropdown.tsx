"use client";

import { useMemo, useState } from "react";
import {
  Bell,
  CheckCheck,
  Trash2,
  Trophy,
  AtSign,
  Clock,
  Info,
} from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { safeHref } from "@/lib/safe-href";
import { useNotifications } from "@/hooks/use-notifications";
import type { AppNotification } from "@/types/notification";
import { useMediaQuery } from "@/hooks/use-media-query";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerTitle,
} from "@/components/ui/drawer";

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function IconForType({ n }: { n: AppNotification }) {
  if (n.avatarUrl)
    return (
      <Avatar className="size-8">
        <AvatarImage src={n.avatarUrl} alt="" />
        <AvatarFallback>{n.icon ?? ""}</AvatarFallback>
      </Avatar>
    );
  const base = "rounded-full flex items-center justify-center size-8";
  switch (n.type) {
    case "achievement":
      return (
        <div className={cn(base, "bg-secondary text-secondary-foreground")}>
          <Trophy className="size-4" />
        </div>
      );
    case "mention":
      return (
        <div className={cn(base, "bg-accent text-accent-foreground")}>
          <AtSign className="size-4" />
        </div>
      );
    case "reminder":
      return (
        <div className={cn(base, "bg-primary text-primary-foreground")}>
          <Clock className="size-4" />
        </div>
      );
    default:
      return (
        <div className={cn(base, "bg-muted text-muted-foreground")}>
          <Info className="size-4" />
        </div>
      );
  }
}

function NotificationItem({
  n,
  onToggleRead,
  onItemOpen,
}: {
  n: AppNotification;
  onToggleRead: (id: string, read: boolean) => void;
  onItemOpen?: () => void;
}) {
  return (
    <div
      className={cn(
        "flex gap-3 p-2 rounded-md transition-colors",
        !n.read && "bg-primary/5 dark:bg-primary/10"
      )}
    >
      <IconForType n={n} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-2">
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{n.title}</div>
            {n.description ? (
              <div className="text-xs text-muted-foreground truncate">
                {n.description}
              </div>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {!n.read ? (
              <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                New
              </Badge>
            ) : null}
            <span className="text-[10px] text-muted-foreground whitespace-nowrap">
              {timeAgo(n.createdAt)}
            </span>
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => onToggleRead(n.id, !n.read)}
          >
            {n.read ? "Mark as unread" : "Mark as read"}
          </Button>
          {(() => {
            const safe = safeHref(n.href);
            return safe ? (
              <Button
                asChild
                variant="secondary"
                size="sm"
                className="h-7 px-2 text-xs"
              >
                <a href={safe} onClick={onItemOpen}>
                  Open
                </a>
              </Button>
            ) : null;
          })()}
        </div>
      </div>
    </div>
  );
}

function NotificationsPanel({
  unreadCount,
  groups,
  onMarkAllRead,
  onClearAll,
  onToggleRead,
  onClose,
}: {
  unreadCount: number;
  groups: {
    all: AppNotification[];
    unread: AppNotification[];
    mentions: AppNotification[];
    rewards: AppNotification[];
  };
  onMarkAllRead: () => void;
  onClearAll: () => void;
  onToggleRead: (id: string, next: boolean) => void;
  onClose: () => void;
}) {
  return (
    <>
      <div className="p-3 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell className="size-4" />
          <div className="font-medium text-sm">Notifications</div>
          {unreadCount > 0 && (
            <Badge variant="destructive" className="ml-1">
              {unreadCount} new
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-xs"
            onClick={onMarkAllRead}
          >
            <CheckCheck className="size-3.5 mr-1" /> Mark all read
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2 text-xs"
            onClick={onClearAll}
          >
            <Trash2 className="size-3.5 mr-1" /> Clear
          </Button>
        </div>
      </div>

      <div className="p-3">
        <Tabs defaultValue="unread">
          <TabsList>
            <TabsTrigger value="unread">Unread</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="mentions">Mentions</TabsTrigger>
            <TabsTrigger value="rewards">Rewards</TabsTrigger>
          </TabsList>

          <TabsContent value="unread">
            {groups.unread.length ? (
              <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1 scrollbar-thin">
                {groups.unread.map((n) => (
                  <NotificationItem
                    key={n.id}
                    n={n}
                    onToggleRead={onToggleRead}
                    onItemOpen={onClose}
                  />
                ))}
              </div>
            ) : (
              <EmptyState label="You're all caught up" />
            )}
          </TabsContent>

          <TabsContent value="all">
            {groups.all.length ? (
              <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1 scrollbar-thin">
                {groups.all.map((n) => (
                  <NotificationItem
                    key={n.id}
                    n={n}
                    onToggleRead={onToggleRead}
                    onItemOpen={onClose}
                  />
                ))}
              </div>
            ) : (
              <EmptyState label="No notifications yet" />
            )}
          </TabsContent>

          <TabsContent value="mentions">
            {groups.mentions.length ? (
              <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1 scrollbar-thin">
                {groups.mentions.map((n) => (
                  <NotificationItem
                    key={n.id}
                    n={n}
                    onToggleRead={onToggleRead}
                    onItemOpen={onClose}
                  />
                ))}
              </div>
            ) : (
              <EmptyState label="No mentions" />
            )}
          </TabsContent>

          <TabsContent value="rewards">
            {groups.rewards.length ? (
              <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1 scrollbar-thin">
                {groups.rewards.map((n) => (
                  <NotificationItem
                    key={n.id}
                    n={n}
                    onToggleRead={onToggleRead}
                    onItemOpen={onClose}
                  />
                ))}
              </div>
            ) : (
              <EmptyState label="No rewards yet" />
            )}
          </TabsContent>
        </Tabs>
      </div>

      <div className="border-t p-2 text-xs text-muted-foreground text-center">
        Tips: You can manage notifications in Settings later.
      </div>
    </>
  );
}

export function NotificationDropdown() {
  const { items, unreadCount, markAllRead, markRead, clearAll, loaded } =
    useNotifications();
  const [open, setOpen] = useState(false);
  const isMobile = useMediaQuery("(max-width: 639px)");

  const groups = useMemo(() => {
    return {
      all: items,
      unread: items.filter((n) => !n.read),
      mentions: items.filter((n) => n.type === "mention"),
      rewards: items.filter((n) => n.type === "achievement"),
    } as const;
  }, [items]);

  const onToggleRead = (id: string, next: boolean) => markRead(id, next);

  if (isMobile) {
    return (
      <>
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 relative"
          onClick={() => setOpen(true)}
        >
          <Bell className="h-4 w-4" />
          <span className="sr-only">Notifications</span>
          {loaded && unreadCount > 0 ? (
            <span className="absolute -top-0.5 -right-0.5 inline-flex min-w-4 h-4 items-center justify-center rounded-full bg-destructive text-[10px] text-destructive-foreground px-1">
              {unreadCount}
            </span>
          ) : null}
        </Button>

        <Drawer
          direction="top"
          open={open}
          onOpenChange={setOpen}
          autoFocus={open}
        >
          <DrawerContent className="max-h-[80vh]">
            <DrawerTitle className="sr-only">Notifications</DrawerTitle>
            <DrawerDescription className="sr-only">
              Your recent notifications
            </DrawerDescription>
            <NotificationsPanel
              unreadCount={unreadCount}
              groups={groups}
              onMarkAllRead={markAllRead}
              onClearAll={clearAll}
              onToggleRead={onToggleRead}
              onClose={() => setOpen(false)}
            />
          </DrawerContent>
        </Drawer>
      </>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="h-9 w-9 relative">
          <Bell className="h-4 w-4" />
          <span className="sr-only">Notifications</span>
          {loaded && unreadCount > 0 ? (
            <span className="absolute -top-0.5 -right-0.5 inline-flex min-w-4 h-4 items-center justify-center rounded-full bg-destructive text-[10px] text-destructive-foreground px-1">
              {unreadCount}
            </span>
          ) : null}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[380px] p-0">
        <NotificationsPanel
          unreadCount={unreadCount}
          groups={groups}
          onMarkAllRead={markAllRead}
          onClearAll={clearAll}
          onToggleRead={onToggleRead}
          onClose={() => setOpen(false)}
        />
      </PopoverContent>
    </Popover>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 text-muted-foreground">
      <Bell className="size-6 mb-2 opacity-70" />
      <div className="text-sm">{label}</div>
    </div>
  );
}
