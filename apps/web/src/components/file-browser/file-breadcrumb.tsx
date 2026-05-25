"use client";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useMe } from "@/lib/api-hooks/use-auth";
import { useNode } from "@/lib/api-hooks/use-nodes";
import { FileIcon } from "./file-icon";

interface FileBreadcrumbProps {
  type: "collection" | "folder" | "deck";
  folderName?: string;
  deckName?: string;
  deckId?: string;
}

export function FileBreadcrumb({
  type,
  folderName,
  deckName,
  deckId,
}: FileBreadcrumbProps) {
  const { data: me } = useMe();
  const { data: deck } = useNode(
    type === "deck" && deckId ? deckId : undefined,
  );
  const { data: parentFolder } = useNode(
    type === "deck" && deck?.parent_node_id ? deck.parent_node_id : undefined,
  );

  const username = me?.name?.trim() || me?.email?.split("@")[0] || "you";
  const avatarUrl = me?.image ?? undefined;

  const resolvedFolderName =
    type === "deck" && parentFolder ? parentFolder.name : folderName;
  const resolvedDeckName =
    type === "deck" && deck ? deck.name : deckName;

  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink href="/profile" className="flex items-center gap-2">
            <Avatar className="h-5 w-5">
              {avatarUrl && <AvatarImage src={avatarUrl} alt={username} />}
              <AvatarFallback className="text-xs">
                {username.slice(0, 2).toUpperCase()}
              </AvatarFallback>
            </Avatar>
            <span className="font-medium">{username}</span>
          </BreadcrumbLink>
        </BreadcrumbItem>

        <BreadcrumbSeparator />

        <BreadcrumbItem>
          <BreadcrumbLink
            href="/"
            className="flex items-center gap-2 overflow-visible"
          >
            <FileIcon
              kind="collection"
              className="h-4 w-4 text-foreground"
              badgeColor="foreground"
            />
            <span>Collection</span>
          </BreadcrumbLink>
        </BreadcrumbItem>

        {type !== "collection" && resolvedFolderName && (
          <>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              {type === "folder" ? (
                <BreadcrumbPage className="flex items-center gap-2 overflow-visible">
                  <FileIcon
                    kind="folder"
                    className="h-4 w-4 text-foreground"
                    badgeColor="foreground"
                  />
                  <span>{resolvedFolderName}</span>
                </BreadcrumbPage>
              ) : (
                <BreadcrumbLink
                  href={
                    parentFolder
                      ? `/folders/${parentFolder.id}`
                      : `/folders/${resolvedFolderName
                          .toLowerCase()
                          .replace(/\s+/g, "-")}`
                  }
                  className="flex items-center gap-2 overflow-visible"
                >
                  <FileIcon
                    kind="folder"
                    className="h-4 w-4 text-foreground"
                    badgeColor="foreground"
                  />
                  <span>{resolvedFolderName}</span>
                </BreadcrumbLink>
              )}
            </BreadcrumbItem>
          </>
        )}

        {type === "deck" && resolvedDeckName && (
          <>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="flex items-center gap-2 overflow-visible">
                <FileIcon
                  kind="deck"
                  className="h-4 w-4 text-foreground"
                  badgeColor="foreground"
                />
                <span>{resolvedDeckName}</span>
              </BreadcrumbPage>
            </BreadcrumbItem>
          </>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
