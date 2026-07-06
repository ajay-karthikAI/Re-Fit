"use client";

type CopyButtonProps = {
  copyKey: string;
  text: string;
  label?: string;
  copiedKey: string | null;
  copy: (key: string, text: string) => void | Promise<void>;
  /** Emphasized styling for the primary copy action on a field. */
  primary?: boolean;
};

export function CopyButton({
  copyKey,
  text,
  label = "Copy",
  copiedKey,
  copy,
  primary = false
}: CopyButtonProps) {
  const copied = copiedKey === copyKey;
  return (
    <button
      type="button"
      data-testid={`copy-${copyKey}`}
      aria-label={label}
      onClick={() => copy(copyKey, text)}
      className={[
        "inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition",
        copied
          ? "border-accent bg-accent/15 text-accent"
          : primary
            ? "border-accent/50 bg-accent/10 text-accent hover:bg-accent/20"
            : "border-border text-subdued hover:border-accent hover:text-text"
      ].join(" ")}
    >
      <span className="font-mono">{copied ? "✓" : "⧉"}</span>
      {copied ? "Copied" : label}
    </button>
  );
}
