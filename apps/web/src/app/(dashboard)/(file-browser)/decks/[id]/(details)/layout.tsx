"use client";

import { use, useMemo } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Grid, List } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

interface Props {
  children: React.ReactNode;
  params: Promise<{
    id: string;
  }>;
}

export default function DetailsLayout({ children, params }: Props) {
  const { id } = use(params);
  const pathname = usePathname();
  const router = useRouter();

  const currentTab = useMemo(() => {
    return pathname.includes("/terms") ? "table" : "terms";
  }, [pathname]);

  const handleTabChange = (value: string) => {
    if (value === "terms") {
      router.push(`/decks/${id}`, { scroll: false });
    } else {
      router.push(`/decks/${id}/terms`, { scroll: false });
    }
  };

  return (
    <Tabs
      value={currentTab}
      onValueChange={handleTabChange}
      className="space-y-6"
    >
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="terms" className="flex items-center gap-2">
          <Grid className="h-4 w-4" />
          Overview
        </TabsTrigger>
        <TabsTrigger value="table" className="flex items-center gap-2">
          <List className="h-4 w-4" />
          Terms
        </TabsTrigger>
      </TabsList>

      <TabsContent value={currentTab} className="space-y-6">
        {children}
      </TabsContent>
    </Tabs>
  );
}
