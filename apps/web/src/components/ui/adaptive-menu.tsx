"use client";

import * as React from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "./dropdown-menu";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "./drawer";
import { useMediaQuery } from "@/hooks/use-media-query";
import { cn } from "@/lib/utils";
import { ChevronLeft } from "lucide-react";

interface AdaptiveMenuProps {
  trigger: React.ReactNode;
  title?: string;
  description?: string;
  children: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

interface AdaptiveMenuContentProps {
  align?: "start" | "center" | "end";
  side?: "bottom" | "top" | "right" | "left";
  className?: string;
  children: React.ReactNode;
}

interface AdaptiveMenuItemProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onSelect"> {
  onSelect?: () => void;
  variant?: "default" | "destructive";
  children: React.ReactNode;
  disabled?: boolean;
}

interface AdaptiveMenuSubProps {
  title: string;
  children: React.ReactNode;
}

type MenuContextType = {
  isDesktop: boolean;
  closeMenu: () => void;
  view: string;
  setView: (view: string) => void;
  history: string[];
  setHistory: React.Dispatch<React.SetStateAction<string[]>>;
  registerView: (id: string, title: string, content: React.ReactNode) => void;
};

const AdaptiveMenuContext = React.createContext<MenuContextType | null>(null);

const useMenu = () => {
  const context = React.useContext(AdaptiveMenuContext);
  if (!context) {
    throw new Error("useMenu must be used within an AdaptiveMenu");
  }
  return context;
};

function AdaptiveMenu({
  trigger,
  title = "Menu",
  description,
  children,
  open,
  onOpenChange,
}: AdaptiveMenuProps) {
  const isDesktop = useMediaQuery("(min-width: 768px)");
  const [internalOpen, setInternalOpen] = React.useState(false);
  const [view, setView] = React.useState("main");
  const [history, setHistory] = React.useState<string[]>([]);
  const [registeredViews, setRegisteredViews] = React.useState<
    Record<string, { title: string; content: React.ReactNode }>
  >({
    main: { title, content: children },
  });

  const isOpen = open ?? internalOpen;
  const setIsOpen = onOpenChange ?? setInternalOpen;

  const closeMenu = React.useCallback(() => {
    setIsOpen(false);
    setTimeout(() => {
      setView("main");
      setHistory([]);
    }, 300);
  }, [setIsOpen]);

  const registerView = React.useCallback(
    (id: string, title: string, content: React.ReactNode) => {
      setRegisteredViews((prev) => ({ ...prev, [id]: { title, content } }));
    },
    []
  );

  const contextValue = React.useMemo(
    () => ({
      isDesktop,
      closeMenu,
      view,
      setView,
      history,
      setHistory,
      registerView,
    }),
    [isDesktop, closeMenu, view, history, registerView]
  );

  const currentView = registeredViews[view] || registeredViews["main"];

  if (isDesktop) {
    return (
      <AdaptiveMenuContext.Provider value={contextValue}>
        <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
          <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
          {children}
        </DropdownMenu>
      </AdaptiveMenuContext.Provider>
    );
  }

  const handleBack = () => {
    const lastView = history[history.length - 1];
    if (lastView) {
      setView(lastView);
      setHistory((prev) => prev.slice(0, -1));
    }
  };

  return (
    <AdaptiveMenuContext.Provider value={contextValue}>
      <Drawer open={isOpen} onOpenChange={setIsOpen} autoFocus={isOpen}>
        <DrawerTrigger asChild>{trigger}</DrawerTrigger>
        <DrawerContent>
          <DrawerHeader className="sr-only">
            <DrawerTitle>{currentView.title}</DrawerTitle>
            <DrawerDescription>
              {description || "Select an option from the menu."}
            </DrawerDescription>
          </DrawerHeader>

          {view !== "main" && (
            <div className="border-b">
              <button
                onClick={handleBack}
                className="flex w-full items-center px-4 py-2 text-left text-sm font-medium text-muted-foreground"
              >
                <ChevronLeft className="mr-2 h-4 w-4" />
                Back
              </button>
            </div>
          )}

          <div className="overflow-auto">{currentView.content}</div>
        </DrawerContent>
      </Drawer>
    </AdaptiveMenuContext.Provider>
  );
}

function AdaptiveMenuContent({
  align = "end",
  side = "bottom",
  className,
  children,
}: AdaptiveMenuContentProps) {
  const { isDesktop } = useMenu();

  if (isDesktop) {
    return (
      <DropdownMenuContent
        align={align}
        side={side}
        className={cn("w-56", className)}
      >
        {children}
      </DropdownMenuContent>
    );
  }

  return <div className="flex flex-col">{children}</div>;
}

function AdaptiveMenuItem({
  onSelect,
  disabled = false,
  variant = "default",
  className,
  children,
  ...props
}: AdaptiveMenuItemProps) {
  const { isDesktop, closeMenu } = useMenu();

  if (isDesktop) {
    return (
      <DropdownMenuItem
        onSelect={onSelect}
        disabled={disabled}
        className={cn(
          variant === "destructive" &&
            "text-destructive focus:text-destructive",
          className
        )}
        {...props}
      >
        {children}
      </DropdownMenuItem>
    );
  }

  const handleMobileClick = () => {
    onSelect?.();
    closeMenu();
  };

  return (
    <button
      onClick={handleMobileClick}
      disabled={disabled}
      className={cn(
        "flex w-full items-center gap-2 px-4 py-2 text-left text-sm transition-colors",
        "hover:bg-muted active:bg-muted/80",
        "disabled:pointer-events-none disabled:opacity-50",
        variant === "destructive" &&
          "text-destructive hover:bg-destructive/10 hover:text-destructive",
        className
      )}
      {...(props as React.ButtonHTMLAttributes<HTMLButtonElement>)}
    >
      {children}
    </button>
  );
}

function AdaptiveMenuLabel({
  className,
  children,
}: React.HTMLAttributes<HTMLDivElement>) {
  const { isDesktop } = useMenu();
  if (isDesktop) {
    return (
      <DropdownMenuLabel className={cn("px-2 py-1.5", className)}>
        {children}
      </DropdownMenuLabel>
    );
  }
  return (
    <div
      className={cn(
        "px-4 py-2 text-sm font-semibold text-muted-foreground",
        className
      )}
    >
      {children}
    </div>
  );
}

function AdaptiveMenuSeparator({
  className,
}: React.HTMLAttributes<HTMLDivElement>) {
  const { isDesktop } = useMenu();
  if (isDesktop) {
    return <DropdownMenuSeparator className={cn("-mx-1 my-1", className)} />;
  }
  return <div className={cn("h-px bg-border my-1", className)} />;
}

function AdaptiveMenuSub({ title, children }: AdaptiveMenuSubProps) {
  const { isDesktop, registerView } = useMenu();
  const subMenuId = React.useId();

  const trigger = React.Children.toArray(children).find(
    (child) =>
      React.isValidElement(child) && child.type === AdaptiveMenuSubTrigger
  );

  const contentElement = React.Children.toArray(children).find(
    (child) =>
      React.isValidElement(child) && child.type === AdaptiveMenuSubContent
  ) as React.ReactElement<{ children?: React.ReactNode }> | undefined;

  const content = contentElement ? contentElement.props.children : null;

  React.useEffect(() => {
    if (!isDesktop && content) {
      registerView(subMenuId, title, content);
    }
  }, [isDesktop, registerView, subMenuId, title, content]);

  if (isDesktop) {
    return <DropdownMenuSub>{children}</DropdownMenuSub>;
  }

  return (
    <>
      {React.cloneElement(
        trigger as React.ReactElement<{ subMenuId?: string }>,
        { subMenuId }
      )}
    </>
  );
}

function AdaptiveMenuSubTrigger({
  className,
  children,
  subMenuId,
}: React.PropsWithChildren<{
  className?: string;
  subMenuId?: string;
}>) {
  const { isDesktop, setView, setHistory, view } = useMenu();

  const handleMobileClick = () => {
    if (subMenuId) {
      setHistory((prev) => [...prev, view]);
      setView(subMenuId);
    }
  };

  if (isDesktop) {
    return (
      <DropdownMenuSubTrigger className={cn("px-2 py-1.5", className)}>
        {children}
      </DropdownMenuSubTrigger>
    );
  }

  return (
    <button
      onClick={handleMobileClick}
      aria-haspopup="true"
      className={cn(
        "flex w-full items-center px-4 py-2 text-left text-sm transition-colors",
        "hover:bg-muted active:bg-muted/80",
        "disabled:pointer-events-none disabled:opacity-50",
        className
      )}
    >
      {children}
      <svg
        className="ml-auto h-4 w-4"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 5l7 7-7 7"
        />
      </svg>
    </button>
  );
}

function AdaptiveMenuSubContent({
  className,
  children,
}: React.PropsWithChildren<{ className?: string }>) {
  const { isDesktop } = useMenu();

  if (isDesktop) {
    return (
      <DropdownMenuSubContent className={cn("w-48", className)}>
        {children}
      </DropdownMenuSubContent>
    );
  }
  return null;
}

export {
  AdaptiveMenu,
  AdaptiveMenuContent,
  AdaptiveMenuItem,
  AdaptiveMenuLabel,
  AdaptiveMenuSeparator,
  AdaptiveMenuSub,
  AdaptiveMenuSubContent,
  AdaptiveMenuSubTrigger,
};
