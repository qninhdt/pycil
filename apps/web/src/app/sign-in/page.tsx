import { signIn } from "@/../auth";

const REASON_COPY: Record<string, string> = {
  token_revoked: "Signed out from all devices.",
  expired: "Session expired, sign in again.",
};

const ERROR_COPY: Record<string, string> = {
  account_deleted: "Your account has been deleted.",
};

export default function SignInPage({
  searchParams,
}: {
  searchParams: { callbackUrl?: string; reason?: string; error?: string };
}) {
  const callbackUrl = searchParams?.callbackUrl ?? "/";
  const banner =
    (searchParams?.error && ERROR_COPY[searchParams.error]) ||
    (searchParams?.reason && REASON_COPY[searchParams.reason]) ||
    null;
  return (
    <main className="flex min-h-svh items-center justify-center px-6">
      <section className="w-full max-w-sm space-y-8 rounded-2xl border border-border bg-card p-8 shadow-sm">
        <header className="space-y-2 text-center">
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
        <form
          action={async () => {
            "use server";
            await signIn("google", { redirectTo: callbackUrl });
          }}
        >
          <button
            type="submit"
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Continue with Google
          </button>
        </form>
      </section>
    </main>
  );
}
