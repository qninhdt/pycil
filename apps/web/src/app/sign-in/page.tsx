import { GraduationCap } from "lucide-react";
import { signIn } from "@/../auth";
import { safeCallbackUrl } from "@/lib/safe-href";

const REASON_COPY: Record<string, string> = {
  token_revoked: "Signed out from all devices.",
  expired: "Session expired, sign in again.",
};

const ERROR_COPY: Record<string, string> = {
  account_deleted: "Your account has been deleted.",
};

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string; reason?: string; error?: string }>;
}) {
  const params = await searchParams;
  const callbackUrl = safeCallbackUrl(params?.callbackUrl);
  const banner =
    (params?.error && ERROR_COPY[params.error]) ||
    (params?.reason && REASON_COPY[params.reason]) ||
    null;
  const useMock = process.env.NEXT_PUBLIC_USE_MOCK === "true";
  return (
    <main className="relative flex min-h-svh items-center justify-center overflow-hidden px-6">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/10 via-background to-background" />
      <section className="relative w-full max-w-sm space-y-8 rounded-2xl border border-border bg-card/80 p-8 shadow-lg backdrop-blur">
        <header className="space-y-3 text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <GraduationCap className="size-6" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Welcome to Pycil</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to continue. Your decks, terms, and study progress live in
            your account.
          </p>
        </header>
        {banner ? (
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-center text-xs text-muted-foreground">
            {banner}
          </div>
        ) : null}
        {useMock ? (
          <div className="space-y-3">
            <a
              href={callbackUrl}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-all hover:bg-primary/90 active:scale-[0.98]"
            >
              Continue as Demo User
            </a>
            <p className="text-center text-xs text-muted-foreground">
              Demo mode — no account needed. Explore every feature with sample
              data.
            </p>
          </div>
        ) : (
          <form
            action={async () => {
              "use server";
              await signIn(process.env.OIDC_PROVIDER_ID ?? "oidc", {
                redirectTo: callbackUrl,
              });
            }}
          >
            <button
              type="submit"
              className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Continue with {process.env.OIDC_PROVIDER_NAME ?? "SSO"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
