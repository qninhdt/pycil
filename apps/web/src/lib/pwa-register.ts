// Service worker registration helper (P11 phase 1).
//
// Call from app layout on the client. Registers /sw.js once per session,
// updates silently on subsequent visits.

export function registerServiceWorker(): void {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch(() => {
        // best-effort: PWA install banner never appears, app still works
      });
  });
}

export function isInstallable(): boolean {
  if (typeof window === "undefined") return false;
  return Boolean((window as any).deferredPwaPrompt);
}

export async function promptInstall(): Promise<"accepted" | "dismissed"> {
  if (typeof window === "undefined") return "dismissed";
  const evt = (window as any).deferredPwaPrompt;
  if (!evt) return "dismissed";
  evt.prompt();
  const { outcome } = await evt.userChoice;
  (window as any).deferredPwaPrompt = null;
  return outcome;
}
