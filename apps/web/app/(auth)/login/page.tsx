import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth/session";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const session = await getSession();
  if (session.isLoggedIn) {
    redirect("/dashboard");
  }

  const { error } = await searchParams;

  return (
    <Card className="w-full">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl font-bold">Welcome to Pycil</CardTitle>
        <CardDescription>
          AI-powered vocabulary learning with FSRS spaced repetition
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive font-medium">
            Authentication failed ({error}). Please try again.
          </div>
        )}
        <a href="/api/auth/login" className={buttonVariants({ size: "lg", className: "w-full" })}>
          Sign in with Google
        </a>
      </CardContent>
    </Card>
  );
}
