import React from "react";

interface FormattedExampleProps {
  text: string;
  className?: string;
}

export function FormattedExample({ text, className }: FormattedExampleProps) {
  if (!text) return null;

  // Regex to match <t inf="...">content</t> or <t>content</t>
  const tagRegex = /<t(?:\s+inf="([^"]*)")?>([\s\S]*?)<\/t>/g;

  const elements: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tagRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      elements.push(text.slice(lastIndex, match.index));
    }

    const [, inf, word] = match;
    elements.push(
      <span
        key={match.index}
        className="font-semibold text-primary underline decoration-primary/40 underline-offset-2"
        title={inf ? `Dạng từ: ${inf}` : undefined}
      >
        {word}
      </span>
    );

    lastIndex = tagRegex.lastIndex;
  }

  if (lastIndex < text.length) {
    elements.push(text.slice(lastIndex));
  }

  return <span className={className}>&ldquo;{elements}&rdquo;</span>;
}
