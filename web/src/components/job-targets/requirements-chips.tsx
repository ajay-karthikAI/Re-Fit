"use client";

type RequirementItem = {
  term: string;
  weight: number;
  evidence: string;
};

type Requirements = {
  hard_skills?: RequirementItem[];
  soft_skills?: RequirementItem[];
  domain_terms?: string[];
  seniority?: string;
  must_haves?: string[];
  nice_to_haves?: string[];
};

function Chip({ item }: { item: RequirementItem }) {
  // Weight drives the accent intensity; evidence is the JD snippet in the tooltip.
  const strong = item.weight >= 0.75;
  return (
    <span
      title={item.evidence}
      className={[
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
        strong
          ? "border-accent/40 bg-accent/10 text-accent"
          : "border-border bg-surface text-subdued"
      ].join(" ")}
    >
      {item.term}
      <span className="font-mono text-[10px] opacity-70">{item.weight.toFixed(2)}</span>
    </span>
  );
}

export function RequirementsChips({ requirements }: { requirements: Requirements | null }) {
  if (!requirements) {
    return (
      <p className="text-sm text-subdued">
        Requirements not extracted yet — generating a kit will extract them.
      </p>
    );
  }

  const hard = requirements.hard_skills ?? [];
  const soft = requirements.soft_skills ?? [];
  const domain = requirements.domain_terms ?? [];
  const must = requirements.must_haves ?? [];
  const nice = requirements.nice_to_haves ?? [];

  return (
    <div className="space-y-5" data-testid="requirements">
      {requirements.seniority ? (
        <p className="text-xs text-subdued">
          Seniority: <span className="font-mono text-text">{requirements.seniority}</span>
        </p>
      ) : null}

      {hard.length > 0 ? (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">Hard skills</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {hard.map((item) => (
              <Chip key={item.term} item={item} />
            ))}
          </div>
        </div>
      ) : null}

      {soft.length > 0 ? (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">Soft skills</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {soft.map((item) => (
              <Chip key={item.term} item={item} />
            ))}
          </div>
        </div>
      ) : null}

      {domain.length > 0 ? (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">Domain terms</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {domain.map((term) => (
              <span
                key={term}
                className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-subdued"
              >
                {term}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {must.length > 0 ? (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">Must-haves</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-text">
            {must.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {nice.length > 0 ? (
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">Nice-to-haves</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-subdued">
            {nice.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
