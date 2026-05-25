"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSeedOnboarding } from "@/lib/api-hooks/use-onboarding";
import { useMe } from "@/lib/api-hooks/use-auth";
import { queryKeys } from "@/lib/api-client/query-keys";

const STORAGE_KEY = "pycil_onboarding_seeded_v1";

export function OnboardingTrigger() {
  const { data: me } = useMe();
  const seed = useSeedOnboarding();
  const qc = useQueryClient();
  const ranRef = useRef(false);

  useEffect(() => {
    if (!me) return;
    if (ranRef.current) return;
    if (typeof window === "undefined") return;

    const flagKey = `${STORAGE_KEY}:${me.id}`;
    if (sessionStorage.getItem(flagKey) === "1") {
      ranRef.current = true;
      return;
    }
    ranRef.current = true;

    seed
      .mutateAsync()
      .then(() => {
        sessionStorage.setItem(flagKey, "1");
        qc.invalidateQueries({ queryKey: queryKeys.nodes.root() });
      })
      .catch(() => {
        ranRef.current = false;
      });
  }, [me, seed, qc]);

  return null;
}
