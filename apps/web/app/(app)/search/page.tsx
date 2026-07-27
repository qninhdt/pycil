"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function SearchPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/library");
  }, [router]);

  return (
    <div className="container max-w-4xl py-12 px-4 text-center">
      <p className="text-muted-foreground">Redirecting to Library...</p>
    </div>
  );
}
