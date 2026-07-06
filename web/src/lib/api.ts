import createClient from "openapi-fetch";

import type { paths } from "@/lib/api-types";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8100";

export const api = createClient<paths>({
  baseUrl: API_BASE_URL,
  // Defer to the live global fetch on each call rather than binding it at
  // client-creation time, so test doubles that replace globalThis.fetch apply.
  fetch: (...args) => globalThis.fetch(...args)
});

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function unwrap<T>(response: {
  data?: T;
  error?: unknown;
  response: Response;
}): Promise<T> {
  if (response.error) {
    const detail = (response.error as { detail?: unknown } | undefined)?.detail;
    throw new ApiError(
      typeof detail === "string" ? detail : "FastAPI returned an error",
      response.response.status
    );
  }
  if (response.data === undefined) {
    throw new ApiError("FastAPI returned an empty response", response.response.status);
  }
  return response.data;
}

export type HealthStatus =
  paths["/health"]["get"]["responses"][200]["content"]["application/json"];

export type DevUser = paths["/users"]["get"]["responses"][200]["content"]["application/json"][number];

export type ApplicationListItem =
  paths["/users/{user_id}/applications"]["get"]["responses"][200]["content"]["application/json"][number];

export type ApplicationStatus = ApplicationListItem["status"];

export type ApplicationUpdate = NonNullable<
  paths["/applications/{application_id}"]["patch"]["requestBody"]
>["content"]["application/json"];

export type ApplicationRead =
  paths["/applications/{application_id}"]["patch"]["responses"][200]["content"]["application/json"];

export type ApplicationKitDetail =
  paths["/applications/{application_id}/kit"]["get"]["responses"][200]["content"]["application/json"];

export type KitFollowup = NonNullable<ApplicationKitDetail["followups"]>[number];

export type FollowupKind = KitFollowup["kind"];

export type FollowupResult =
  paths["/applications/{application_id}/followups"]["post"]["responses"][200]["content"]["application/json"];

export type RenderResponse =
  paths["/versions/{version_id}/render"]["post"]["responses"][200]["content"]["application/json"];

export async function getHealth(): Promise<HealthStatus> {
  return unwrap(await api.GET("/health"));
}

export async function listUsers(): Promise<DevUser[]> {
  return unwrap(await api.GET("/users"));
}

export async function listApplications(userId: string): Promise<ApplicationListItem[]> {
  return unwrap(
    await api.GET("/users/{user_id}/applications", {
      params: { path: { user_id: userId } }
    })
  );
}

export async function updateApplication(
  applicationId: string,
  body: ApplicationUpdate
): Promise<ApplicationRead> {
  return unwrap(
    await api.PATCH("/applications/{application_id}", {
      params: { path: { application_id: applicationId } },
      body
    })
  );
}

export async function getApplicationKit(applicationId: string): Promise<ApplicationKitDetail> {
  return unwrap(
    await api.GET("/applications/{application_id}/kit", {
      params: { path: { application_id: applicationId } }
    })
  );
}

export async function createFollowup(
  applicationId: string,
  kind: FollowupKind
): Promise<FollowupResult> {
  return unwrap(
    await api.POST("/applications/{application_id}/followups", {
      params: { path: { application_id: applicationId } },
      body: { kind }
    })
  );
}

export async function renderVersion(
  versionId: string,
  format: "pdf" | "docx"
): Promise<RenderResponse> {
  return unwrap(
    await api.POST("/versions/{version_id}/render", {
      params: { path: { version_id: versionId } },
      body: { format }
    })
  );
}

// --- Job targets -----------------------------------------------------------

export type JobTargetListItem =
  paths["/users/{user_id}/job-targets"]["get"]["responses"][200]["content"]["application/json"][number];

export type JobTargetRead =
  paths["/job-targets/{job_target_id}"]["get"]["responses"][200]["content"]["application/json"];

export type JobTargetCreate = NonNullable<
  paths["/users/{user_id}/job-targets"]["post"]["requestBody"]
>["content"]["application/json"];

export type KitRequest = NonNullable<
  paths["/job-targets/{job_target_id}/kit"]["post"]["requestBody"]
>["content"]["application/json"];

export type KitResult =
  paths["/job-targets/{job_target_id}/kit"]["post"]["responses"][200]["content"]["application/json"];

export type Tone = NonNullable<KitRequest["tone"]>;
export type TemplateId = NonNullable<KitRequest["template"]>;

export async function listJobTargets(userId: string): Promise<JobTargetListItem[]> {
  return unwrap(
    await api.GET("/users/{user_id}/job-targets", {
      params: { path: { user_id: userId } }
    })
  );
}

export async function getJobTarget(jobTargetId: string): Promise<JobTargetRead> {
  return unwrap(
    await api.GET("/job-targets/{job_target_id}", {
      params: { path: { job_target_id: jobTargetId } }
    })
  );
}

export async function createJobTarget(
  userId: string,
  body: JobTargetCreate
): Promise<JobTargetRead> {
  return unwrap(
    await api.POST("/users/{user_id}/job-targets", {
      params: { path: { user_id: userId } },
      body
    })
  ) as Promise<JobTargetRead>;
}

export async function extractRequirements(jobTargetId: string) {
  return unwrap(
    await api.POST("/job-targets/{job_target_id}/extract", {
      params: { path: { job_target_id: jobTargetId } }
    })
  );
}

export async function generateKit(jobTargetId: string, body: KitRequest): Promise<KitResult> {
  return unwrap(
    await api.POST("/job-targets/{job_target_id}/kit", {
      params: { path: { job_target_id: jobTargetId } },
      body
    })
  );
}

// --- Versions --------------------------------------------------------------

export type ResumeVersionListItem =
  paths["/profiles/{profile_id}/versions"]["get"]["responses"][200]["content"]["application/json"][number];

export type EnrichedVersionDiff =
  paths["/versions/{version_id}/diff"]["get"]["responses"][200]["content"]["application/json"];

export async function listVersions(profileId: string): Promise<ResumeVersionListItem[]> {
  return unwrap(
    await api.GET("/profiles/{profile_id}/versions", {
      params: { path: { profile_id: profileId } }
    })
  );
}

export async function getVersionDiff(versionId: string): Promise<EnrichedVersionDiff> {
  return unwrap(
    await api.GET("/versions/{version_id}/diff", {
      params: { path: { version_id: versionId } }
    })
  );
}

export async function compareVersions(
  fromVersionId: string,
  toVersionId: string
): Promise<EnrichedVersionDiff> {
  return unwrap(
    await api.GET("/versions/{from_version_id}/compare/{to_version_id}", {
      params: { path: { from_version_id: fromVersionId, to_version_id: toVersionId } }
    })
  );
}

// --- Profile ---------------------------------------------------------------

export type ProfileRead =
  paths["/users/{user_id}/profile"]["get"]["responses"][200]["content"]["application/json"];

export type StructuredResume = ProfileRead["data"];

export async function getProfile(userId: string): Promise<ProfileRead> {
  return unwrap(
    await api.GET("/users/{user_id}/profile", {
      params: { path: { user_id: userId } }
    })
  );
}

/**
 * Save the canonical profile. Returns the validation errors mapped to field
 * locations on a 422 so the form can attach them, instead of throwing.
 */
export type FieldError = { loc: (string | number)[]; msg: string };

export async function saveProfile(
  userId: string,
  resume: StructuredResume
): Promise<{ ok: true; data: ProfileRead } | { ok: false; errors: FieldError[] }> {
  const response = await api.PUT("/users/{user_id}/profile", {
    params: { path: { user_id: userId } },
    body: resume
  });
  if (response.error) {
    const detail = (response.error as { detail?: unknown }).detail;
    if (Array.isArray(detail)) {
      return { ok: false, errors: detail as FieldError[] };
    }
    throw new ApiError(
      typeof detail === "string" ? detail : "Failed to save profile",
      response.response.status
    );
  }
  return { ok: true, data: response.data as ProfileRead };
}

// --- Applications (create) -------------------------------------------------

export type ApplicationCreate = NonNullable<
  paths["/users/{user_id}/applications"]["post"]["requestBody"]
>["content"]["application/json"];

export async function createApplication(
  userId: string,
  body: ApplicationCreate
): Promise<ApplicationRead> {
  return unwrap(
    await api.POST("/users/{user_id}/applications", {
      params: { path: { user_id: userId } },
      body
    })
  ) as Promise<ApplicationRead>;
}

// --- Uploads (e2e / profile bootstrap) -------------------------------------

export type UploadResult =
  paths["/users/{user_id}/uploads"]["post"]["responses"][201]["content"]["application/json"];

export async function uploadResume(userId: string, file: File): Promise<UploadResult> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE_URL}/users/${userId}/uploads`, {
    method: "POST",
    body
  });
  if (!response.ok) {
    throw new ApiError("Upload failed", response.status);
  }
  return (await response.json()) as UploadResult;
}

export async function parseUpload(uploadId: string) {
  return unwrap(
    await api.POST("/uploads/{upload_id}/parse", {
      params: { path: { upload_id: uploadId } }
    })
  );
}
