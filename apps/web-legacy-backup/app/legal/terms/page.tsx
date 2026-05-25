export const metadata = { title: "Terms — Pycil" };

export default function TermsPage() {
  return (
    <main className="mx-auto max-w-2xl p-8 prose prose-sm">
      <h1>Terms of Service</h1>
      <p>Last updated: 2026-05-25</p>

      <h2>Use</h2>
      <p>
        Pycil is provided as-is for personal, non-commercial vocabulary
        learning. Don&apos;t use it to scrape, abuse, or attempt to extract
        data from upstream LLM providers.
      </p>

      <h2>No warranty</h2>
      <p>
        AI-generated definitions and questions may be inaccurate. Always
        cross-check important learning content with a dictionary you
        trust.
      </p>

      <h2>Liability</h2>
      <p>
        We provide no warranty and accept no liability for losses, damages,
        or learning outcomes arising from use of this service.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms; continued use after changes means
        acceptance.
      </p>
    </main>
  );
}
