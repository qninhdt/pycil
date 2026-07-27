export type AsyncTaskStatus = "queued" | "running" | "succeeded" | "failed" | "expired";

export interface AsyncTaskSnapshot {
  schema: "async-task.v1";
  eventId: string;
  taskId: string;
  kind: string;
  status: AsyncTaskStatus;
  version: number;
  result: Record<string, unknown> | null;
  errorCode: string | null;
}

export function reduceAsyncTaskSnapshot(
  current: AsyncTaskSnapshot | null,
  incoming: unknown,
  taskId: string
): AsyncTaskSnapshot | null {
  if (!isAsyncTaskSnapshot(incoming) || incoming.taskId !== taskId) {
    return current;
  }
  if (!current) {
    return incoming;
  }
  if (incoming.eventId === current.eventId || incoming.version <= current.version) {
    return current;
  }
  return incoming;
}

function isAsyncTaskSnapshot(value: unknown): value is AsyncTaskSnapshot {
  if (!value || typeof value !== "object") return false;
  const snapshot = value as Record<string, unknown>;
  return (
    snapshot.schema === "async-task.v1" &&
    typeof snapshot.eventId === "string" &&
    typeof snapshot.taskId === "string" &&
    typeof snapshot.kind === "string" &&
    isAsyncTaskStatus(snapshot.status) &&
    typeof snapshot.version === "number" &&
    (snapshot.result === null || typeof snapshot.result === "object") &&
    (snapshot.errorCode === null || typeof snapshot.errorCode === "string")
  );
}

function isAsyncTaskStatus(value: unknown): value is AsyncTaskStatus {
  return value === "queued" || value === "running" || value === "succeeded" || value === "failed" || value === "expired";
}
