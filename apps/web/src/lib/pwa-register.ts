// Service worker registration helper.
//
// Call from app layout on the client. Registers /sw.js once per session,
// updates silently on subsequent visits.

// `beforeinstallprompt` is not in the standard DOM lib types yet.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

type WindowWithInstallPrompt = Window & {
  deferredPwaPrompt?: BeforeInstallPromptEvent | null;
};

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
  return Boolean((window as WindowWithInstallPrompt).deferredPwaPrompt);
}

export async function promptInstall(): Promise<"accepted" | "dismissed"> {
  if (typeof window === "undefined") return "dismissed";
  const evt = (window as WindowWithInstallPrompt).deferredPwaPrompt;
  if (!evt) return "dismissed";
  evt.prompt();
  const { outcome } = await evt.userChoice;
  (window as WindowWithInstallPrompt).deferredPwaPrompt = null;
  return outcome;
}
