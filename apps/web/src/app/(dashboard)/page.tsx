"use client";

import Link from "next/link";
import { ArrowRight, GraduationCap, Layers, Sparkles } from "lucide-react";
import { useMe } from "@/lib/api-hooks/use-auth";
import { Button } from "@/components/ui/button";

const FEATURES = [
  {
    icon: Layers,
    title: "Organize effortlessly",
    description: "Group terms into decks and folders that mirror how you study.",
  },
  {
    icon: Sparkles,
    title: "AI-crafted definitions",
    description: "Every term gets clear meanings, paraphrases, and examples.",
  },
  {
    icon: GraduationCap,
    title: "Master with spaced repetition",
    description: "ELO-driven sessions surface exactly what you need to review.",
  },
] as const;

export default function Home() {
  const { data: me } = useMe();
  const collectionHref = me ? `/u/${me.id}/collection` : "/sign-in";
  return (
    <div className="space-y-12">
      <section className="relative overflow-hidden rounded-3xl border bg-gradient-to-br from-primary/10 via-card to-card px-6 py-16 text-center sm:py-20">
        <div className="mx-auto max-w-2xl space-y-6">
          <span className="inline-flex items-center gap-2 rounded-full border bg-background/60 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur">
            <Sparkles className="size-3.5 text-primary" />
            AI-powered vocabulary learning
          </span>
          <h1 className="text-balance text-4xl font-bold tracking-tight sm:text-5xl">
            Start learning today
          </h1>
          <p className="text-pretty text-lg text-muted-foreground">
            Create flashcards, organize your study materials, and master any
            subject with spaced repetition built for retention.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Button asChild size="lg">
              <Link href={collectionHref}>
                Browse collection
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {FEATURES.map((feature) => (
          <div
            key={feature.title}
            className="group rounded-2xl border bg-card p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
          >
            <div className="mb-3 inline-flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary/15">
              <feature.icon className="size-5" />
            </div>
            <h3 className="font-semibold">{feature.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {feature.description}
            </p>
          </div>
        ))}
      </section>
    </div>
  );
}
