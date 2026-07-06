"use client";

import type { EnrichedVersionDiff } from "@/lib/api";

function RequirementTag({ requirement }: { requirement: string | null | undefined }) {
  if (!requirement) {
    return null;
  }
  return (
    <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[10px] text-accent">
      targets: {requirement}
    </span>
  );
}

type ExperienceGroup = NonNullable<EnrichedVersionDiff["experience_groups"]>[number];
type Change = NonNullable<ExperienceGroup["changes"]>[number];

function BulletPair({ change }: { change: Change }) {
  const before = typeof change.before === "string" ? change.before : JSON.stringify(change.before);
  const after = typeof change.after === "string" ? change.after : JSON.stringify(change.after);
  return (
    <div className="rounded-md border border-border bg-surface p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-mono text-[10px] text-subdued">{change.ref}</span>
        <RequirementTag requirement={change.requirement_targeted} />
      </div>
      <p className="rounded bg-red-950/20 px-2 py-1 text-sm text-red-200/80 line-through decoration-red-400/40">
        {before}
      </p>
      <p className="mt-1 rounded bg-accent/10 px-2 py-1 text-sm text-text">{after}</p>
    </div>
  );
}

export function DiffView({ diff }: { diff: EnrichedVersionDiff }) {
  const summary = diff.summary;
  const experienceGroups = diff.experience_groups ?? [];
  const projectGroups = diff.project_groups ?? [];
  const sectionReorderings = diff.section_reorderings ?? [];
  const otherChanges = diff.other_changes ?? [];
  const requirementsTargeted = summary.requirements_targeted ?? [];
  const noChanges =
    experienceGroups.length === 0 &&
    projectGroups.length === 0 &&
    sectionReorderings.length === 0 &&
    otherChanges.length === 0;

  return (
    <div className="space-y-6" data-testid="diff-view">
      <div className="flex flex-wrap gap-2">
        <span className="rounded-md border border-border bg-muted px-3 py-1.5 text-xs text-text">
          {summary.bullets_rewritten} rewritten
        </span>
        <span className="rounded-md border border-border bg-muted px-3 py-1.5 text-xs text-subdued">
          {summary.bullets_unchanged} unchanged (collapsed)
        </span>
        {summary.skills_reordered ? (
          <span className="rounded-md border border-border bg-muted px-3 py-1.5 text-xs text-text">
            skills reordered
          </span>
        ) : null}
        {requirementsTargeted.map((requirement) => (
          <span
            key={requirement}
            className="rounded-md bg-accent/15 px-3 py-1.5 font-mono text-[11px] text-accent"
          >
            {requirement}
          </span>
        ))}
      </div>

      {noChanges ? (
        <p className="text-sm text-subdued">No bullet rewrites in this version.</p>
      ) : null}

      {experienceGroups.map((group) => (
        <div key={group.experience_ref}>
          <h3 className="text-sm font-medium text-text">
            {group.title ?? "Role"}
            {group.company ? <span className="text-subdued"> · {group.company}</span> : null}
          </h3>
          <div className="mt-2 space-y-2">
            {(group.changes ?? []).map((change, index) => (
              <BulletPair key={`${group.experience_ref}-${index}`} change={change} />
            ))}
          </div>
        </div>
      ))}

      {projectGroups.map((group) => (
        <div key={group.project_ref}>
          <h3 className="text-sm font-medium text-text">{group.name ?? "Project"}</h3>
          <div className="mt-2 space-y-2">
            {(group.changes ?? []).map((change, index) => (
              <BulletPair key={`${group.project_ref}-${index}`} change={change} />
            ))}
          </div>
        </div>
      ))}

      {sectionReorderings.length > 0 ? (
        <div>
          <h3 className="text-sm font-medium text-text">Section reorderings</h3>
          <div className="mt-2 space-y-2">
            {sectionReorderings.map((change, index) => (
              <BulletPair key={`section-${index}`} change={change} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
