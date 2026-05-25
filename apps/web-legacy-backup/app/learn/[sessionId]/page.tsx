import { LearningSessionRunner } from "@/components/learning-session-runner";

export default async function LearnSessionPage(props: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await props.params;
  return (
    <main className="mx-auto max-w-2xl p-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold">Study session</h1>
        <p className="text-sm text-gray-500">
          Answer 2 first-attempts correctly per term to mark it reviewed.
        </p>
      </header>
      <LearningSessionRunner sessionId={sessionId} />
    </main>
  );
}
