"use client";

import { usePathname } from "next/navigation";
import { FileBreadcrumb } from "@/components/file-browser";

export default function FileBrowserLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  const getBreadcrumbProps = () => {
    if (pathname.includes("/collection")) {
      return { type: "collection" as const };
    }

    if (pathname.startsWith("/folders/")) {
      const folderId = pathname.split("/folders/")[1];
      const folderName = decodeURIComponent(folderId)
        .replace(/-/g, " ")
        .toUpperCase();
      return { type: "folder" as const, folderName };
    }

    if (pathname.startsWith("/decks/")) {
      const deckId = pathname.split("/decks/")[1].split("/")[0];
      return { type: "deck" as const, deckId };
    }

    return null;
  };

  const breadcrumbProps = getBreadcrumbProps();

  return (
    <div className="space-y-6">
      {breadcrumbProps && <FileBreadcrumb {...breadcrumbProps} />}
      {children}
    </div>
  );
}
