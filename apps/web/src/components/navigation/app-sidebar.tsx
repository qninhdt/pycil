"use client";

import React, { memo, useMemo, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { SheetClose } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import {
  User,
  GraduationCap,
  SidebarClose,
  SidebarOpen,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

// --- Type Definitions ---
interface MenuItem {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly href?: string;
  readonly onClick?: () => void;
  readonly title?: string;
  readonly id: string; // Added for better React keys
}

interface SidebarProps {
  readonly isCollapsed?: boolean;
  readonly onToggleCollapse?: () => void;
  readonly isMobile?: boolean;
}

interface SidebarItemProps {
  readonly item: MenuItem;
  readonly isCollapsed: boolean;
  readonly isActive: boolean;
  readonly isMobile?: boolean;
}

interface NavListProps {
  readonly items: readonly MenuItem[];
  readonly isCollapsed: boolean;
  readonly pathname: string;
  readonly isMobile?: boolean;
}

// --- Constants ---
const STATIC_FOOTER_ITEMS: readonly MenuItem[] = [
  { id: "account", icon: User, label: "My Account", href: "/profile" },
] as const;

// --- Optimized Sub-components ---

/**
 * Memoized sidebar item component for better performance
 */
const SidebarItem = memo<SidebarItemProps>(
  ({ item, isCollapsed, isActive, isMobile = false }) => {
    const commonClasses = useMemo(
      () =>
        cn(
          "w-full h-10 text-sm font-medium transition-colors",
          isCollapsed ? "justify-center px-0" : "justify-start px-3 gap-3",
          isActive && "bg-primary/10 text-primary hover:bg-primary/20"
        ),
      [isCollapsed, isActive]
    );

    const title = item.title ?? (isCollapsed ? item.label : undefined);

    const content = useMemo(
      () => (
        <>
          <item.icon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          {!isCollapsed && (
            <span className="truncate transition-all duration-300">
              {item.label}
            </span>
          )}
        </>
      ),
      [item, isCollapsed]
    );

    if (item.href) {
      const linkElement = (
        <Button
          variant={isActive ? "secondary" : "ghost"}
          className={commonClasses}
          asChild
          title={title}
          aria-label={item.label}
          aria-current={isActive ? "page" : undefined}
        >
          <Link href={item.href}>{content}</Link>
        </Button>
      );

      return isMobile ? (
        <SheetClose asChild>{linkElement}</SheetClose>
      ) : (
        linkElement
      );
    }

    return (
      <Button
        variant="ghost"
        className={commonClasses}
        onClick={item.onClick}
        title={title}
        aria-label={item.label}
      >
        {content}
      </Button>
    );
  }
);

SidebarItem.displayName = "SidebarItem";

/**
 * Memoized navigation list component
 */
const NavList = memo<NavListProps>(
  ({ items, isCollapsed, pathname, isMobile = false }) => {
    const containerClasses = useMemo(
      () => cn("space-y-1", isCollapsed ? "px-2" : "px-3"),
      [isCollapsed]
    );

    return (
      <nav className={containerClasses} role="navigation">
        {items.map((item) => (
          <SidebarItem
            key={item.id}
            item={item}
            isCollapsed={isCollapsed}
            isActive={pathname === item.href}
            isMobile={isMobile}
          />
        ))}
      </nav>
    );
  }
);

NavList.displayName = "NavList";

/**
 * Brand logo component
 */
const SidebarBrand = memo<{ isCollapsed: boolean; isMobile: boolean }>(
  ({ isCollapsed, isMobile }) => {
    const brandContent = useMemo(
      () => (
        <>
          <GraduationCap
            className="h-6 w-6 text-primary flex-shrink-0"
            aria-hidden="true"
          />
          <span
            className={cn(
              "text-lg font-semibold",
              isCollapsed && !isMobile && "hidden"
            )}
          >
            Pycil
          </span>
        </>
      ),
      [isCollapsed, isMobile]
    );

    const linkElement = (
      <Link
        href="/"
        className="flex items-center gap-2"
        aria-label="Pycil Home"
      >
        {brandContent}
      </Link>
    );

    return isMobile ? (
      <SheetClose asChild>{linkElement}</SheetClose>
    ) : (
      linkElement
    );
  }
);

SidebarBrand.displayName = "SidebarBrand";

/**
 * Main sidebar content component with optimized performance
 */
const SidebarContent = memo<SidebarProps>(
  ({ isCollapsed = false, onToggleCollapse, isMobile = false }) => {
    const pathname = usePathname();

    // Memoize footer items to prevent unnecessary re-renders
    const footerItems = useMemo(() => {
      const items: MenuItem[] = [...STATIC_FOOTER_ITEMS];
      if (!isMobile && onToggleCollapse) {
        items.push({
          id: "collapse-toggle",
          icon: isCollapsed ? SidebarOpen : SidebarClose,
          label: "Collapse",
          onClick: onToggleCollapse,
          title: isCollapsed ? "Expand sidebar" : "Collapse sidebar",
        });
      }
      return items;
    }, [isMobile, onToggleCollapse, isCollapsed]);

    const containerClasses = useMemo(
      () =>
        cn(
          "flex h-full flex-col bg-card border-r transition-all duration-300",
          isMobile ? "w-full" : isCollapsed ? "w-16" : "w-64"
        ),
      [isMobile, isCollapsed]
    );

    const headerClasses = useMemo(
      () =>
        cn(
          "flex h-16 items-center",
          isCollapsed && !isMobile ? "justify-center" : "justify-between px-4"
        ),
      [isCollapsed, isMobile]
    );

    return (
      <div
        className={containerClasses}
        role="complementary"
        aria-label="Sidebar"
      >
        {/* Header */}
        <div className={headerClasses}>
          <SidebarBrand isCollapsed={isCollapsed} isMobile={isMobile} />
          {isMobile && (
            <SheetClose asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                aria-label="Close sidebar"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </Button>
            </SheetClose>
          )}
        </div>

        {/* Main Navigation */}
        <div className="flex-1 overflow-auto py-2 scrollbar-thin border-t">
          <NavList
            items={footerItems}
            isCollapsed={isCollapsed && !isMobile}
            pathname={pathname}
            isMobile={isMobile}
          />
        </div>

        {/* Footer */}
        <div className="border-t space-y-4 py-2" />
      </div>
    );
  }
);

SidebarContent.displayName = "SidebarContent";

/**
 * Main sidebar wrapper component with state management
 */
export const AppSidebar = memo<{
  readonly isCollapsed?: boolean;
  readonly onToggleCollapse?: () => void;
  readonly isMobile?: boolean;
}>(
  ({
    isCollapsed: controlledCollapsed,
    onToggleCollapse: controlledToggle,
    isMobile = false,
  }) => {
    const [internalCollapsed, setInternalCollapsed] = useState(false);

    // Use external controlled state if provided, otherwise use internal state
    const isCollapsed =
      controlledCollapsed !== undefined
        ? controlledCollapsed
        : internalCollapsed;

    const handleToggleCollapse = useCallback(() => {
      if (controlledToggle) {
        controlledToggle();
      } else {
        setInternalCollapsed((prev) => !prev);
      }
    }, [controlledToggle]);

    const onToggleCollapse = controlledToggle || handleToggleCollapse;

    return (
      <SidebarContent
        isCollapsed={isCollapsed}
        onToggleCollapse={onToggleCollapse}
        isMobile={isMobile}
      />
    );
  }
);

AppSidebar.displayName = "AppSidebar";
