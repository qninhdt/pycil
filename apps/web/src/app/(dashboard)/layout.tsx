"use client";

import { AppSidebar } from "@/components/navigation";
import { AppHeader } from "@/components/navigation";
import { Button } from "@/components/ui/button";
import { Menu } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useAppSettings } from "@/providers";
import { OnboardingTrigger } from "@/components/onboarding/onboarding-trigger";

interface AppLayoutProps {
  children: React.ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  const { sidebarCollapsed, setSidebarCollapsed, isLoaded } = useAppSettings();

  if (!isLoaded) {
    return null;
  }

  const handleToggleCollapse = () => {
    setSidebarCollapsed(!sidebarCollapsed);
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="flex">
        {/* Desktop Sidebar */}
        <div className="hidden lg:block fixed inset-y-0 z-50">
          <AppSidebar
            isCollapsed={sidebarCollapsed}
            onToggleCollapse={handleToggleCollapse}
          />
        </div>

        {/* Main Content */}
        <div
          className={cn(
            "flex-1 flex flex-col layout-transition",
            "lg:ml-64", // Default margin for expanded sidebar
            sidebarCollapsed && "lg:ml-16" // Reduced margin for collapsed sidebar
          )}
        >
          {/* Header with Mobile Sidebar Trigger */}
          <header className="sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
            <div className="flex h-16 items-center px-4 gap-4">
              {/* Mobile/Tablet Sidebar Trigger */}
              <div className="lg:hidden">
                <Sheet>
                  <SheetTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-9 w-9">
                      <Menu className="h-5 w-5" />
                      <span className="sr-only">Toggle navigation menu</span>
                    </Button>
                  </SheetTrigger>
                  <SheetContent
                    side="left"
                    className="p-0 w-full sm:w-3/4 sm:max-w-md [&>button]:hidden"
                  >
                    <SheetTitle className="sr-only">Navigation Menu</SheetTitle>
                    <SheetDescription className="sr-only">
                      Mobile navigation menu
                    </SheetDescription>
                    <div className="relative h-full">
                      <AppSidebar isMobile={true} />
                    </div>
                  </SheetContent>
                </Sheet>
              </div>

              {/* Header Content */}
              <div className="flex-1 flex items-center">
                <AppHeader />
              </div>
            </div>
          </header>

          {/* Page Content */}
          <main className="flex-1 p-4 lg:p-6">
            <div className="max-w-4xl mx-auto">{children}</div>
          </main>
        </div>
      </div>
      <OnboardingTrigger />
    </div>
  );
}
