/**
 * Sign-in has no shell: no rail, no tab bar, no header actions. There is nothing
 * to navigate to yet, and a tab bar whose destinations all bounce back here is
 * worse than no tab bar.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">{children}</div>
    </div>
  )
}
