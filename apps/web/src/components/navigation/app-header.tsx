"use client";

import React, { memo, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { UserDropdown } from "./user-dropdown";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandList,
} from "@/components/ui/command";
import { Search } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTrigger,
  DialogTitle,
  DialogHeader,
  DialogDescription,
} from "@/components/ui/dialog";
import { NotificationDropdown } from "@/components/notifications";

const SearchDialog = memo<{
  open: boolean;
  onOpenChange: (open: boolean) => void;
}>(({ open, onOpenChange }) => {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          className="w-full justify-start h-9 bg-muted/50 hover:bg-muted text-muted-foreground text-sm"
          aria-label="Search for term decks, classes"
        >
          <Search className="h-4 w-4 mr-2 flex-shrink-0" aria-hidden="true" />
          <span className="truncate hidden sm:inline">
            Search for term decks, classes...
          </span>
          <span className="truncate sm:hidden">Search...</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="p-0" showCloseButton={false}>
        <DialogHeader className="sr-only">
          <DialogTitle>Search</DialogTitle>
        </DialogHeader>
        <DialogDescription className="sr-only">
          Search for term decks, classes, and more
        </DialogDescription>
        <Command className="rounded-lg border shadow-md md:min-w-[450px]">
          <CommandInput placeholder="Type a command or search..." />
          <CommandList className="h-[400px] max-h-[400px] overflow-y-auto scrollbar-thin">
            <CommandEmpty>No results found.</CommandEmpty>
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  );
});

SearchDialog.displayName = "SearchDialog";

const ActionButtons = memo(() => (
  <div className="flex items-center space-x-1 sm:space-x-2">
    <NotificationDropdown />
    <UserDropdown />
  </div>
));

ActionButtons.displayName = "ActionButtons";

/**
 * Optimized main header component
 */
export const AppHeader = memo(() => {
  const [dialogOpen, setDialogOpen] = useState(false);

  const handleDialogOpenChange = useCallback((open: boolean) => {
    setDialogOpen(open);
  }, []);

  return (
    <div className="flex items-center justify-between w-full">
      {/* Search Bar */}
      <div className="flex-1 max-w-md mr-4">
        <SearchDialog open={dialogOpen} onOpenChange={handleDialogOpenChange} />
      </div>

      {/* Right Side Actions */}
      <ActionButtons />
    </div>
  );
});

AppHeader.displayName = "AppHeader";
