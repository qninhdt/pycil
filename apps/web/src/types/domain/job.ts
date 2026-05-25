import type { ISODateString } from "./node";

export type JobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface JobRow {
  id: string;
  type: string;
  status: JobStatus;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}
