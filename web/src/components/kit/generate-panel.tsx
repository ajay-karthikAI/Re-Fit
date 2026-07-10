"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { type KitResult, type TemplateId, type Tone, generateKit, getExistingKit } from "@/lib/api";
import { KitResultView } from "@/components/kit/kit-result-view";
import { ProgressStepper, STAGES, STAGE_INTERVAL_MS } from "@/components/kit/kit-progress";
import { useToast } from "@/components/ui/toast";

const TONES: { id: Tone; label: string }[] = [
  { id: "standard", label: "Standard" },
  { id: "direct", label: "Direct" },
  { id: "warm", label: "Warm" }
];

const TEMPLATES: { id: TemplateId; label: string }[] = [
  { id: "classic", label: "Classic" },
  { id: "compact", label: "Compact" },
  { id: "modern", label: "Modern" },
  { id: "mono", label: "Mono" }
];

export function GeneratePanel({
  jobTargetId,
  hasRequirements
}: {
  jobTargetId: string;
  hasRequirements: boolean;
}) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [tone, setTone] = useState<Tone>("standard");
  const [template, setTemplate] = useState<TemplateId>("classic");
  const [activeStage, setActiveStage] = useState(0);
  const [result, setResult] = useState<KitResult | null>(null);

  // If a kit was already generated for this job target (e.g. the feed's
  // one-click Generate-kit just landed here), show it straight away rather than
  // the generate form — this is the kit view the whole flow aims at.
  const existingKit = useQuery({
    queryKey: ["existing-kit", jobTargetId],
    queryFn: () => getExistingKit(jobTargetId)
  });

  const mutation = useMutation({
    mutationFn: () => generateKit(jobTargetId, { tone, template, force: false }),
    onMutate: () => setActiveStage(0),
    onSuccess: (kit) => {
      setActiveStage(STAGES.length);
      setResult(kit);
      queryClient.invalidateQueries({ queryKey: ["job-target", jobTargetId] });
      queryClient.invalidateQueries({ queryKey: ["job-targets"] });
    },
    onError: (error: Error) => toast(`Kit generation failed: ${error.message}`)
  });

  // Advance the staged indicator while the request is in flight.
  useEffect(() => {
    if (!mutation.isPending) {
      return;
    }
    const timer = setInterval(() => {
      setActiveStage((stage) => Math.min(stage + 1, STAGES.length - 1));
    }, STAGE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [mutation.isPending]);

  const shownKit = result ?? existingKit.data ?? null;
  if (shownKit) {
    return <KitResultView kit={shownKit} jobTargetId={jobTargetId} />;
  }

  // Avoid flashing the generate form before we know whether a kit already exists.
  if (existingKit.isLoading && !mutation.isPending) {
    return (
      <div className="rounded-xl border border-border bg-muted p-6">
        <p className="text-sm text-subdued">Loading kit…</p>
      </div>
    );
  }

  if (mutation.isPending) {
    return (
      <div className="rounded-xl border border-border bg-muted p-6">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">Generating kit</p>
        <p className="mt-1 text-sm text-subdued">
          Tailoring, scoring, writing, and rendering — this takes a moment.
        </p>
        <div className="mt-5">
          <ProgressStepper activeStage={activeStage} />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-muted p-6">
      <h2 className="text-lg font-semibold text-text">Generate application kit</h2>
      <p className="mt-1 text-sm text-subdued">
        Tailors your resume, writes a verified cover letter, and renders both.
      </p>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">Cover letter tone</p>
          <div className="mt-2 inline-flex rounded-md border border-border bg-surface p-0.5">
            {TONES.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setTone(option.id)}
                className={[
                  "rounded px-3 py-1.5 text-xs transition",
                  tone === option.id ? "bg-muted text-accent" : "text-subdued hover:text-text"
                ].join(" ")}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="font-mono text-xs uppercase tracking-[0.16em] text-subdued">Resume template</p>
          <div className="mt-2 flex flex-wrap gap-1">
            {TEMPLATES.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setTemplate(option.id)}
                className={[
                  "rounded-md border px-3 py-1.5 text-xs transition",
                  template === option.id
                    ? "border-accent/50 bg-accent/10 text-accent"
                    : "border-border text-subdued hover:text-text"
                ].join(" ")}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {!hasRequirements ? (
        <p className="mt-4 text-xs text-subdued">
          Requirements haven&apos;t been extracted yet — generating the kit will extract them first.
        </p>
      ) : null}

      <button
        type="button"
        data-testid="generate-kit"
        onClick={() => mutation.mutate()}
        className="mt-5 rounded-[10px] bg-gold-gradient px-5 py-2.5 text-sm font-bold text-background transition enabled:hover:-translate-y-0.5 enabled:hover:shadow-gold"
      >
        Generate kit
      </button>
    </div>
  );
}
