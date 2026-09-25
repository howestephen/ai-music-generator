export type Control = {
  default: number;
  minimum: number;
  maximum: number | null;
  step: number;
  label: string;
  info: string;
  integer: boolean;
};

export type ModelInfo = {
  name: string;
  model_id: string;
  licence: string;
  notes: string;
  available: boolean;
  max_duration: number;
  prompt_style: string;
  prompt_hint: string;
  supports_lyrics: boolean;
  supports_editing: boolean;
  voice_choices: string[];
  voice_info: string;
  duration: Control;
  steps: Control | null;
  guidance: Control | null;
};

export type Bootstrap = {
  default_model: string;
  models: ModelInfo[];
  genres: string[];
  characters: string[];
  mood_default: string;
};

export type Track = {
  name: string;
  title: string;
  genre: string | null;
  duration: number | null;
  requested_duration: number | null;
  audit_status: string;
  audit_error: string | null;
  backend: string;
  seed: number | null;
  prompt: string;
  generated_at: string;
  rating: "keep" | "discard" | null;
  sample_rate: number | null;
  elapsed_seconds: number | null;
  steps: number | null;
  guidance: number | null;
  lyrics: string;
  model: string | null;
  audio: string;
  peaks: number[];
};

export type Job = {
  id: string;
  status: string;
  progress: number;
  elapsed_seconds?: number;
  expected_seconds?: number;
  status_text: string;
  model: string;
  prompt: string;
  duration: number;
  seed: number;
  error?: string | null;
  queue_position?: number;
};

export type Pending = {
  stem: string;
  title: string;
  name: string;
  seconds_left: number;
};

export type LibraryState = {
  queue: Job[];
  signature: string;
  pending: Pending[];
  tracks?: Track[];
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof data.error === "string" ? data.error : `Request failed (${response.status})`);
  }
  return data as T;
}

export function loadBootstrap() {
  return request<Bootstrap>("/api/bootstrap");
}

export function loadOptions(genre: string) {
  const query = new URLSearchParams({ genre });
  return request<{ moods: string[]; instruments: string[]; bpm: number | null; duration: number | null }>(
    `/api/options?${query}`,
  );
}

export function composePrompt(body: Record<string, unknown>) {
  return request<{ prompt: string }>("/api/prompt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function generate(body: Record<string, unknown>) {
  return request<{ status: string; seed: number; queue: Job[] }>("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function remix(body: FormData | Record<string, unknown>) {
  if (body instanceof FormData) {
    return request<{ status: string; queue: Job[] }>("/api/remix", { method: "POST", body });
  }
  return request<{ status: string; queue: Job[] }>("/api/remix", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function loadState(signature: string) {
  const query = new URLSearchParams();
  if (signature) query.set("signature", signature);
  return request<LibraryState>(`/api/state?${query}`);
}

export function moveJob(id: string, direction: number) {
  return request<{ queue: Job[] }>("/api/queue/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, direction }),
  });
}

export function removeJob(id: string) {
  return request<{ queue: Job[] }>("/api/queue/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
}

export function rateTrack(name: string, rating: string | null) {
  return request<LibraryState>("/api/tracks/rating", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, rating }),
  });
}

export function deleteTrack(name: string) {
  return request<LibraryState>("/api/tracks/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function undoDelete(stem: string) {
  return request<LibraryState>("/api/tracks/undo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stem }),
  });
}
