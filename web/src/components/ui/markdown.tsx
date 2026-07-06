/**
 * Minimal markdown renderer for generated prose previews (cover letters,
 * follow-up emails). The generators emit plain paragraphs, occasional bold or
 * italic emphasis, and simple dash lists — nothing more, so no dependency.
 */

const INLINE_TOKEN = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;

function inline(text: string): React.ReactNode[] {
  return text.split(INLINE_TOKEN).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    return <span key={index}>{part}</span>;
  });
}

export function MarkdownProse({ markdown }: { markdown: string }) {
  const blocks = markdown
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div className="space-y-3 text-sm leading-6 text-text">
      {blocks.map((block, index) => {
        const lines = block.split("\n");
        if (lines.every((line) => line.trimStart().startsWith("- "))) {
          return (
            <ul key={index} className="list-disc space-y-1 pl-5">
              {lines.map((line, lineIndex) => (
                <li key={lineIndex}>{inline(line.trimStart().slice(2))}</li>
              ))}
            </ul>
          );
        }
        return <p key={index}>{inline(lines.join(" "))}</p>;
      })}
    </div>
  );
}
