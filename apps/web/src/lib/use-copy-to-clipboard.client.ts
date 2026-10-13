"use client";

import { useEffect, useRef, useState } from "react";

export type UseCopyToClipboardOptions = {
  copiedDuration?: number;
};

export const useCopyToClipboard = ({
  copiedDuration = 3000,
}: UseCopyToClipboardOptions = {}) => {
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const scopeGenerationRef = useRef(0);

  useEffect(
    () => () => {
      scopeGenerationRef.current += 1;
      if (copiedTimerRef.current === undefined) return;

      clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = undefined;
    },
    [],
  );

  const copyToClipboard = (value: string) => {
    if (!value || typeof navigator === "undefined" || !navigator.clipboard) {
      return Promise.resolve(false);
    }

    const scopeGeneration = scopeGenerationRef.current;
    return navigator.clipboard.writeText(value).then(
      () => {
        if (scopeGeneration !== scopeGenerationRef.current) return false;

        if (copiedTimerRef.current !== undefined) {
          clearTimeout(copiedTimerRef.current);
        }
        setIsCopied(true);
        copiedTimerRef.current = setTimeout(() => {
          copiedTimerRef.current = undefined;
          setIsCopied(false);
        }, copiedDuration);
        return true;
      },
      () => false,
    );
  };

  return { isCopied, copyToClipboard };
};
