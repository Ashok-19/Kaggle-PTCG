export type RecordValue = Record<string, unknown>;

export type Page = {
  items: RecordValue[];
  total: number;
};

export type Overview = {
  objective: string;
  current_gate: RecordValue | null;
  latest_reports: RecordValue[];
  recent_incidents: RecordValue[];
  jobs: RecordValue[];
  active_jobs: number;
  runtime: RecordValue;
  data_health: RecordValue;
  champion: null;
  challenger: null;
  anchor: null;
};

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

export function asText(value: unknown, fallback = "UNKNOWN"): string {
  return typeof value === "string" && value.length ? value : fallback;
}

export function statusClass(value: unknown): string {
  return `status status-${asText(value).toLowerCase().replaceAll("_", "-")}`;
}
