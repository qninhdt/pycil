"use client";

import React, { createContext, useContext, ReactNode } from "react";
import { useLocalStorage } from "@/hooks/use-local-storage";
import type { ViewMode } from "@/types";

interface AppSettingsContextType {
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  isLoaded: boolean;
}

const AppSettingsContext = createContext<AppSettingsContextType | undefined>(
  undefined
);

interface AppSettingsProviderProps {
  children: ReactNode;
}

export const AppSettingsProvider = ({ children }: AppSettingsProviderProps) => {
  const [sidebarCollapsed, setSidebarCollapsed, sidebarLoaded] =
    useLocalStorage<boolean>("sidebar-collapsed", false);
  const [viewMode, setViewMode, viewModeLoaded] = useLocalStorage<ViewMode>(
    "view-mode",
    "list"
  );

  const isLoaded = sidebarLoaded && viewModeLoaded;

  const value: AppSettingsContextType = {
    sidebarCollapsed,
    setSidebarCollapsed,
    viewMode,
    setViewMode,
    isLoaded,
  };

  return (
    <AppSettingsContext.Provider value={value}>
      {children}
    </AppSettingsContext.Provider>
  );
};

export const useAppSettings = () => {
  const context = useContext(AppSettingsContext);
  if (context === undefined) {
    throw new Error(
      "useAppSettings must be used within an AppSettingsProvider"
    );
  }
  return context;
};
