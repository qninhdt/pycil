import { SignIn } from "@clerk/nextjs"

export default function LoginPage() {
  return (
    <div className="flex w-full max-w-sm flex-col items-center justify-center gap-6 py-8">
      <div className="flex flex-col gap-2 text-center">
        <h1 className="font-serif text-2xl font-semibold">Pycil</h1>
        <p className="text-sm text-muted-foreground">
          A vocabulary trainer that schedules what you are about to forget.
        </p>
      </div>
      <SignIn routing="hash" />
    </div>
  )
}
