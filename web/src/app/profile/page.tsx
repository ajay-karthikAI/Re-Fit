"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  type FieldError,
  type StructuredResume,
  getProfile,
  parseUpload,
  saveProfile,
  uploadResume
} from "@/lib/api";
import { useDevUser } from "@/components/providers/dev-user-provider";
import { useToast } from "@/components/ui/toast";

// Loosened working type: the form mutates a structured resume by path.
type AnyResume = StructuredResume & Record<string, unknown>;

/** Map FastAPI 422 loc paths (["body","experience",0,"bullets",1]) to a key. */
function errorKey(loc: (string | number)[]): string {
  return loc.filter((part) => part !== "body").join(".");
}

/** Blank optional strings must become null so EmailStr/HttpUrl validation is skipped. */
function normalizeForSave(resume: AnyResume): StructuredResume {
  const contact = resume.contact as Record<string, unknown>;
  const cleanedContact: Record<string, unknown> = { ...contact };
  for (const key of ["phone", "location", "linkedin_url", "github_url", "portfolio_url"]) {
    if (!cleanedContact[key]) {
      cleanedContact[key] = null;
    }
  }
  const experience = (resume.experience as Record<string, unknown>[]).map((item) => ({
    ...item,
    end_date: item.end_date ? item.end_date : null,
    location: item.location ? item.location : null
  }));
  return {
    ...resume,
    contact: cleanedContact,
    summary: resume.summary ? resume.summary : null,
    experience
  } as unknown as StructuredResume;
}

function Field({
  label,
  value,
  onChange,
  error,
  placeholder
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-subdued">
        {label}
      </span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={[
          "mt-1 w-full rounded-md border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent",
          error ? "border-red-500/60" : "border-border"
        ].join(" ")}
      />
      {error ? <span className="mt-1 block text-xs text-red-300">{error}</span> : null}
    </label>
  );
}

export default function ProfilePage() {
  const { selectedUserId } = useDevUser();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [resume, setResume] = useState<AnyResume | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const profileQuery = useQuery({
    queryKey: ["profile", selectedUserId],
    queryFn: () => getProfile(selectedUserId as string),
    enabled: selectedUserId !== null,
    retry: false
  });

  useEffect(() => {
    if (profileQuery.data) {
      setResume(profileQuery.data.data as AnyResume);
    }
  }, [profileQuery.data]);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const upload = await uploadResume(selectedUserId as string, file);
      await parseUpload(upload.upload_id);
    },
    onSuccess: () => {
      toast("Resume parsed into your profile.", "success");
      queryClient.invalidateQueries({ queryKey: ["profile", selectedUserId] });
    },
    onError: (error: Error) => toast(`Parse failed: ${error.message}`)
  });

  const saveMutation = useMutation({
    mutationFn: () => saveProfile(selectedUserId as string, normalizeForSave(resume as AnyResume)),
    onSuccess: (outcome) => {
      if (outcome.ok) {
        setErrors({});
        toast("Profile saved.", "success");
        queryClient.invalidateQueries({ queryKey: ["profile", selectedUserId] });
      } else {
        const mapped: Record<string, string> = {};
        for (const item of outcome.errors as FieldError[]) {
          mapped[errorKey(item.loc)] = item.msg;
        }
        setErrors(mapped);
        toast(`${outcome.errors.length} validation error(s) — see highlighted fields.`);
      }
    },
    onError: (error: Error) => toast(`Save failed: ${error.message}`)
  });

  const notFound = profileQuery.isError;
  const contact = (resume?.contact ?? {}) as Record<string, string>;

  const update = useMemo(
    () => (mutator: (draft: AnyResume) => void) => {
      setResume((current) => {
        if (!current) {
          return current;
        }
        const next = structuredClone(current);
        mutator(next);
        return next;
      });
    },
    []
  );

  if (profileQuery.isLoading) {
    return <p className="text-sm text-subdued">Loading profile…</p>;
  }

  return (
    <section className="space-y-6">
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-accent">Profile</p>
        <h1 className="mt-3 text-3xl font-semibold text-text">Canonical resume</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-subdued">
          The single source of truth for every tailored version. Nothing here is invented — edit
          only what you actually did.
        </p>
      </div>

      <div className="rounded-lg border border-border bg-muted p-4">
        <p className="text-sm text-text">
          {notFound
            ? "No profile yet — upload a resume to parse it."
            : "Replace by uploading a new resume:"}
        </p>
        <input
          type="file"
          accept=".pdf,.docx"
          data-testid="resume-upload"
          disabled={uploadMutation.isPending || !selectedUserId}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              uploadMutation.mutate(file);
            }
          }}
          className="mt-2 block text-sm text-subdued file:mr-3 file:rounded-md file:border file:border-border file:bg-surface file:px-3 file:py-1.5 file:text-xs file:text-text"
        />
        {uploadMutation.isPending ? (
          <p className="mt-2 text-xs text-accent">Parsing resume…</p>
        ) : null}
      </div>

      {resume ? (
        <form
          className="space-y-8"
          onSubmit={(event) => {
            event.preventDefault();
            saveMutation.mutate();
          }}
        >
          <fieldset className="space-y-4 rounded-lg border border-border bg-muted p-5">
            <legend className="px-1 text-sm font-medium text-text">Contact</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Full name"
                value={contact.full_name ?? ""}
                error={errors["contact.full_name"]}
                onChange={(value) =>
                  update((draft) => ((draft.contact as Record<string, unknown>).full_name = value))
                }
              />
              <Field
                label="Email"
                value={contact.email ?? ""}
                error={errors["contact.email"]}
                onChange={(value) =>
                  update((draft) => ((draft.contact as Record<string, unknown>).email = value))
                }
              />
              <Field
                label="Phone"
                value={contact.phone ?? ""}
                error={errors["contact.phone"]}
                onChange={(value) =>
                  update((draft) => ((draft.contact as Record<string, unknown>).phone = value))
                }
              />
              <Field
                label="Location"
                value={contact.location ?? ""}
                error={errors["contact.location"]}
                onChange={(value) =>
                  update((draft) => ((draft.contact as Record<string, unknown>).location = value))
                }
              />
              <Field
                label="LinkedIn URL"
                value={contact.linkedin_url ?? ""}
                error={errors["contact.linkedin_url"]}
                onChange={(value) =>
                  update(
                    (draft) => ((draft.contact as Record<string, unknown>).linkedin_url = value)
                  )
                }
              />
              <Field
                label="GitHub URL"
                value={contact.github_url ?? ""}
                error={errors["contact.github_url"]}
                onChange={(value) =>
                  update((draft) => ((draft.contact as Record<string, unknown>).github_url = value))
                }
              />
            </div>
            <label className="block">
              <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-subdued">
                Summary
              </span>
              <textarea
                value={(resume.summary as string) ?? ""}
                onChange={(event) => update((draft) => (draft.summary = event.target.value))}
                className="mt-1 h-20 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text outline-none focus:border-accent"
              />
              {errors["summary"] ? (
                <span className="mt-1 block text-xs text-red-300">{errors["summary"]}</span>
              ) : null}
            </label>
          </fieldset>

          <fieldset className="space-y-4 rounded-lg border border-border bg-muted p-5">
            <legend className="px-1 text-sm font-medium text-text">Experience</legend>
            {(resume.experience as Record<string, unknown>[]).map((item, index) => (
              <div key={index} className="space-y-3 rounded-md border border-border bg-surface p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field
                    label="Company"
                    value={(item.company as string) ?? ""}
                    error={errors[`experience.${index}.company`]}
                    onChange={(value) =>
                      update(
                        (draft) =>
                          ((draft.experience as Record<string, unknown>[])[index].company = value)
                      )
                    }
                  />
                  <Field
                    label="Title"
                    value={(item.title as string) ?? ""}
                    error={errors[`experience.${index}.title`]}
                    onChange={(value) =>
                      update(
                        (draft) =>
                          ((draft.experience as Record<string, unknown>[])[index].title = value)
                      )
                    }
                  />
                  <Field
                    label="Start (YYYY-MM)"
                    value={(item.start_date as string) ?? ""}
                    error={errors[`experience.${index}.start_date`]}
                    onChange={(value) =>
                      update(
                        (draft) =>
                          ((draft.experience as Record<string, unknown>[])[index].start_date =
                            value)
                      )
                    }
                  />
                  <Field
                    label="End (YYYY-MM, blank = present)"
                    value={(item.end_date as string) ?? ""}
                    error={errors[`experience.${index}.end_date`]}
                    onChange={(value) =>
                      update(
                        (draft) =>
                          ((draft.experience as Record<string, unknown>[])[index].end_date = value)
                      )
                    }
                  />
                </div>
                <label className="block">
                  <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-subdued">
                    Bullets (one per line)
                  </span>
                  <textarea
                    value={((item.bullets as string[]) ?? []).join("\n")}
                    onChange={(event) =>
                      update(
                        (draft) =>
                          ((draft.experience as Record<string, unknown>[])[index].bullets =
                            event.target.value
                              .split("\n")
                              .map((line) => line.trim())
                              .filter(Boolean))
                      )
                    }
                    className={[
                      "mt-1 h-28 w-full rounded-md border bg-background px-3 py-2 text-sm text-text outline-none focus:border-accent",
                      errors[`experience.${index}.bullets`]
                        ? "border-red-500/60"
                        : "border-border"
                    ].join(" ")}
                  />
                  {errors[`experience.${index}.bullets`] ? (
                    <span className="mt-1 block text-xs text-red-300">
                      {errors[`experience.${index}.bullets`]}
                    </span>
                  ) : null}
                </label>
              </div>
            ))}
          </fieldset>

          <fieldset className="space-y-4 rounded-lg border border-border bg-muted p-5">
            <legend className="px-1 text-sm font-medium text-text">Skills</legend>
            {(resume.skills as Record<string, unknown>[]).map((group, index) => (
              <div key={index} className="grid gap-3 sm:grid-cols-[1fr_2fr]">
                <Field
                  label="Category"
                  value={(group.category as string) ?? ""}
                  error={errors[`skills.${index}.category`]}
                  onChange={(value) =>
                    update(
                      (draft) =>
                        ((draft.skills as Record<string, unknown>[])[index].category = value)
                    )
                  }
                />
                <Field
                  label="Items (comma-separated)"
                  value={((group.items as string[]) ?? []).join(", ")}
                  error={errors[`skills.${index}.items`]}
                  onChange={(value) =>
                    update(
                      (draft) =>
                        ((draft.skills as Record<string, unknown>[])[index].items = value
                          .split(",")
                          .map((item) => item.trim())
                          .filter(Boolean))
                    )
                  }
                />
              </div>
            ))}
          </fieldset>

          <div className="flex items-center gap-3">
            <button
              type="submit"
              data-testid="save-profile"
              disabled={saveMutation.isPending}
              className="rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-background transition hover:bg-accent/90 disabled:opacity-50"
            >
              {saveMutation.isPending ? "Saving…" : "Save profile"}
            </button>
            {Object.keys(errors).length > 0 ? (
              <span className="text-xs text-red-300">
                {Object.keys(errors).length} field(s) need fixing.
              </span>
            ) : null}
          </div>
        </form>
      ) : null}
    </section>
  );
}
