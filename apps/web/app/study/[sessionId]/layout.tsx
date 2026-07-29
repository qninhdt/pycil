/**
 * The study shell, which is deliberately no shell at all.
 *
 * This route sits outside the `(app)` group on purpose: no header, no navigation, no
 * assistant launcher. A session is one question at a time, and every affordance that
 * is not the question or the two controls acting on it is a way to lose the thread.
 *
 * Providers are not mounted here. The query cache, the stores, and the realtime
 * connection all live in the root layout, so this route reads the same ones the shell
 * does — which is what lets a pending grade started here settle in the activity centre
 * after the learner walks away.
 */
export default function StudyLayout({ children }: { children: React.ReactNode }) {
  return children
}
