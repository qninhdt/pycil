"use client";

import { useMutation } from "@tanstack/react-query";
import * as onboardingApi from "@/lib/api-client/onboarding";

export function useSeedOnboarding() {
  return useMutation({ mutationFn: onboardingApi.seed });
}
