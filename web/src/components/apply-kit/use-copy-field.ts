"use client";

import { useCallback, useRef, useState } from "react";

import { useToast } from "@/components/ui/toast";

// Speed-run UI: the confirmation is fast and low-friction — a brief checkmark on
// the button plus a short-lived toast, never a silent copy.
export const COPY_FEEDBACK_MS = 1500;

/**
 * One-click copy with per-field feedback. `copiedKey` names the field whose
 * button should currently show its checkmark, so a field can host multiple copy
 * buttons (e.g. "Copy" vs "Copy as plain text") that light up independently.
 */
export function useCopyField() {
  const { toast } = useToast();
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const copy = useCallback(
    async (key: string, text: string) => {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      toast("Copied ✓", "success", COPY_FEEDBACK_MS);
      if (timer.current) {
        clearTimeout(timer.current);
      }
      timer.current = setTimeout(() => {
        setCopiedKey((current) => (current === key ? null : current));
      }, COPY_FEEDBACK_MS);
    },
    [toast]
  );

  return { copy, copiedKey };
}
