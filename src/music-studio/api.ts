import type { SongForm, Track } from "./model";
export type BackendStatus = {
  connected: boolean;
  generation: boolean;
  model: string;
  covers: boolean;
  writing: boolean;
};
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function request<T>(
  path: string,
  body?: unknown,
  method = body === undefined ? "GET" : "POST",
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(path === "/openai/login" || path === "/providers/probe" ? 65000 : 15000),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new ApiError(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg).join(" ")
          : "Music service request failed.",
      response.status,
    );
  }
  return data as T;
}
export const musicApi = {
  health: () => request<BackendStatus>("/health"),
  library: () => request<{ tracks: Track[] }>("/library?include_deleted=true"),
  projects: () =>
    request<{ projects: { id: string; name: string }[] }>("/projects"),
  createProject: (name: string) =>
    request<{ id: string; name: string }>("/projects", { name }),
  libraryAction: (
    ids: string[],
    action: "move" | "trash" | "restore",
    project?: string,
  ) =>
    request<{ tracks: Track[] }>("/library/actions", {
      ids,
      action,
      ...(project === undefined ? {} : { project }),
    }),
  generate: (requestId: string, form: SongForm) =>
    request<{ tracks: Track[]; requestId: string; reused: boolean }>(
      "/generations",
      { requestId, form },
    ),
  patch: (
    id: string,
    patch: Partial<Pick<Track, "title" | "project" | "favorite">>,
  ) => request<Track>(`/takes/${id}`, patch, "PATCH"),
  cancel: (id: string) => request(`/takes/${id}/cancel`, {}),
  retry: (id: string) => request(`/takes/${id}/retry`, {}),
  plan: (id: string) =>
    request<{ abc: string; reviewable: boolean }>(`/takes/${id}/plan`),
  continuePlan: (id: string, abc?: string) =>
    request(`/takes/${id}/continue`, abc === undefined ? {} : { abc }),
};
