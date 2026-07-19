export type RecordValue = Record<string, unknown>;

export type Overview = {
  objective: string;
  current_gate: RecordValue | null;
  active_gates: RecordValue[];
  latest_completed_gate: RecordValue | null;
  latest_reports: RecordValue[];
  recent_incidents: RecordValue[];
  jobs: RecordValue[];
  active_jobs: number;
  runtime: RecordValue;
  costs: RecordValue;
  data_health: RecordValue;
  progress: { passed: number; total: number };
  champion: RecordValue | null;
  challenger: RecordValue | null;
  anchor: RecordValue | null;
};

export type DashboardState = {
  generated_at_utc: string | null;
  overview: Overview;
  review: RecordValue[];
  gates: RecordValue[];
  events: RecordValue[];
  decisions: RecordValue[];
  reports: RecordValue[];
  tasks: RecordValue[];
  hypotheses: RecordValue[];
  experiments: RecordValue[];
  runs: RecordValue[];
  replays: RecordValue[];
  decks: RecordValue[];
  evaluations: RecordValue[];
  submissions: RecordValue[];
  jobs: RecordValue[];
  artifacts: RecordValue[];
  learning: RecordValue[];
  costs: RecordValue;
};

export type EvidencePayload = {
  source_path: string;
  source_sha256: string;
  text: string;
  truncated: boolean;
};

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export function asText(value: unknown, fallback = "UNKNOWN"): string {
  return typeof value === "string" && value.length ? value : fallback;
}

export function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export function statusClass(value: unknown): string {
  return `status status-${asText(value).toLowerCase().replaceAll("_", "-")}`;
}
