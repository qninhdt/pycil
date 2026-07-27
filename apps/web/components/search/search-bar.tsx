"use client";

import React, { useEffect, useState } from "react";
import { Search, X, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  isLoading?: boolean;
  placeholder?: string;
}

export function SearchBar({
  value,
  onChange,
  isLoading = false,
  placeholder = "Search Cambridge dictionary or enter a word...",
}: SearchBarProps) {
  const [internalValue, setInternalValue] = useState(value);

  // Sync internal value when controlled prop changes externally
  useEffect(() => {
    setInternalValue(value);
  }, [value]);

  // Debounce internal value changes to parent
  useEffect(() => {
    const timer = setTimeout(() => {
      onChange(internalValue);
    }, 300);

    return () => clearTimeout(timer);
  }, [internalValue, onChange]);

  return (
    <div className="relative w-full">
      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-muted-foreground">
        {isLoading ? (
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
        ) : (
          <Search className="h-5 w-5" />
        )}
      </div>
      <Input
        type="text"
        value={internalValue}
        onChange={(e) => setInternalValue(e.target.value)}
        placeholder={placeholder}
        className="pl-11 pr-10 py-6 text-base shadow-sm transition-all focus-visible:ring-2"
        autoComplete="off"
        spellCheck={false}
      />
      {internalValue && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => {
            setInternalValue("");
            onChange("");
          }}
          className="absolute inset-y-0 right-1 my-auto h-8 w-8 text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Clear search</span>
        </Button>
      )}
    </div>
  );
}
