"use client";

import Link from "next/link";
import { ChevronRight, Home, Folder } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

interface BreadcrumbItemType {
  id?: string;
  name: string;
}

interface BreadcrumbNavProps {
  items?: BreadcrumbItemType[];
}

export function BreadcrumbNav({ items = [] }: BreadcrumbNavProps) {
  return (
    <Breadcrumb className="mb-6">
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink render={<Link href="/library" />}>
            <span className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors">
              <Home className="h-4 w-4" />
              <span>Library</span>
            </span>
          </BreadcrumbLink>
        </BreadcrumbItem>

        {items.map((item, index) => {
          const isLast = index === items.length - 1;

          return (
            <div key={item.id || index} className="inline-flex items-center gap-1.5">
              <BreadcrumbSeparator>
                <ChevronRight className="h-4 w-4" />
              </BreadcrumbSeparator>
              <BreadcrumbItem>
                {isLast ? (
                  <BreadcrumbPage className="font-semibold flex items-center gap-1.5 text-foreground">
                    <Folder className="h-4 w-4 text-primary" />
                    <span>{item.name}</span>
                  </BreadcrumbPage>
                ) : (
                  <BreadcrumbLink render={<Link href={`/library?folderId=${item.id}`} />}>
                    <span className="text-muted-foreground hover:text-foreground transition-colors">
                      {item.name}
                    </span>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </div>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
