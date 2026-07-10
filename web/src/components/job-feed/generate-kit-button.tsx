"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { createJobTargetFromPosting, generateKit } from "@/lib/api";
import { ProgressStepper, STAGES, STAGE_INTERVAL_MS } from "@/components/kit/kit-progress";
import { useToast } from "@/components/ui/toast";

/**
 * THE one-click action. Under the hood: materialise the posting into a job
 * target (source_ats from its board), run the existing kit pipeline, then land
 * on the kit view. Reuses Phase 2's staged progress so the moment feels instant
 * even though a real pipeline runs underneath.
 */
export function GenerateKitButton({
  postingId,
  userId
}: {
  postingId: string;
  userId: string;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [activeStage, setActiveStage] = useState(0);

  const mutation = useMutation({
    mutationFn: async () => {
      const target = await createJobTargetFromPosting(postingId, userId);
      await generateKit(target.id, { tone: "standard", force: false });
      return target.id;
    },
    onMutate: () => setActiveStage(0),
    onSuccess: (jobTargetId) => {
      setActiveStage(STAGES.length);
      queryClient.invalidateQueries({ queryKey: ["job-targets", userId] });
      // Land straight on the freshly-generated kit — the payoff moment.
      router.push(`/job-targets/${jobTargetId}`);
    },
    onError: (error: Error) => toast(`Kit generation failed: ${error.message}`)
  });

  useEffect(() => {
    if (!mutation.isPending) {
      return;
    }
    const timer = setInterval(() => {
      setActiveStage((stage) => Math.min(stage + 1, STAGES.length - 1));
    }, STAGE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [mutation.isPending]);

  if (mutation.isPending || mutation.isSuccess) {
    return (
      <div
        className="rounded-lg border border-border bg-surface p-4"
        data-testid={`generating-${postingId}`}
      >
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-accent">
          Generating kit
        </p>
        <div className="mt-3">
          <ProgressStepper activeStage={activeStage} />
        </div>
      </div>
    );
  }

  return (
    <button
      type="button"
      data-testid={`generate-kit-${postingId}`}
      onClick={() => mutation.mutate()}
      className="rounded-[10px] bg-gold-gradient px-4 py-2 text-sm font-bold text-background transition enabled:hover:-translate-y-0.5 enabled:hover:shadow-gold"
    >
      Generate kit
    </button>
  );
}
