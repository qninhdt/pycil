import Link from "next/link"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { SignInIcon, WarningCircleIcon } from "@/lib/icons"

export const metadata = { title: "Sign in" }

/**
 * Every failure the auth routes can redirect here with. Each one says what to do
 * next, because "authentication failed" tells a person nothing they can act on.
 *
 * An unrecognised code falls through to a generic message rather than being
 * echoed: the value arrives in a URL anyone can edit, so rendering it verbatim
 * would put attacker-chosen text on the page.
 */
const ERROR_MESSAGES: Record<string, string> = {
  auth_init_failed: "Sign-in could not be started. Try again in a moment.",
  network_error: "The sign-in service could not be reached. Check your connection.",
  invalid_callback_params: "That sign-in link was incomplete. Start again.",
  token_exchange_failed: "Sign-in could not be completed. Start again.",
  profile_fetch_failed: "Signed in, but your profile could not be loaded. Try again.",
  callback_internal_error: "Something went wrong while signing you in. Try again.",
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>
}) {
  const { error } = await searchParams
  const message = error
    ? (ERROR_MESSAGES[error] ?? "Sign-in did not complete. Try again.")
    : null

  return (
    <div className="flex w-full max-w-sm flex-col gap-8">
      <div className="flex flex-col gap-2">
        {/* The wordmark is this screen's only title, so it carries the h1 rather
            than being decorative text above an unlabelled page. Serif here is the
            brand wordmark, which is the one non-lexical serif the audit allows. */}
        <h1 className="font-serif text-2xl font-semibold">Pycil</h1>
        <p className="text-sm text-muted-foreground">
          A vocabulary trainer that schedules what you are about to forget.
        </p>
      </div>

      {message ? (
        <Alert variant="destructive">
          <WarningCircleIcon />
          <AlertTitle>Could not sign in</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      ) : null}

      {/* A plain link, not a button with a click handler: sign-in is a navigation
          to the BFF route, which redirects to the provider. */}
      <Button render={<a href="/api/auth/login" />} size="lg">
        <SignInIcon data-icon="inline-start" />
        Continue
      </Button>

      <p className="text-sm text-muted-foreground">
        You can also{" "}
        <Link href="/library" className="underline underline-offset-3">
          browse the library
        </Link>{" "}
        without an account. Studying and adding words need one.
      </p>
    </div>
  )
}
