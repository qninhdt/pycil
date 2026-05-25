"use client";

import Link from "next/link";
import { useMe } from "@/lib/api-hooks/use-auth";

export default function Home() {
  const { data: me } = useMe();
  const collectionHref = me ? `/u/${me.id}/collection` : "/sign-in";
  return (
    <div className="space-y-6">
      <div className="text-center py-12">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl font-bold mb-4">Start Learning Today</h2>
          <p className="text-muted-foreground text-lg mb-8">
            Create flashcards, organize your study materials, and master any
            subject with our powerful learning platform.
          </p>
          <div className="flex gap-4 justify-center">
            <Link
              href={collectionHref}
              className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
            >
              Browse Collection
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
