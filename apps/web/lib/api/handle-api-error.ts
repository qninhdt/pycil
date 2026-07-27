import { redirect } from "next/navigation";
import { ApiError } from "./errors";

export type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string; code: string };

export async function handleAction<T>(fn: () => Promise<T>): Promise<ActionResult<T>> {
  try {
    const data = await fn();
    return { success: true, data };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      redirect("/login");
    }
    if (err instanceof ApiError) {
      return { success: false, error: err.message, code: err.code };
    }
    return {
      success: false,
      error: err instanceof Error ? err.message : "An unexpected error occurred",
      code: "unknown",
    };
  }
}
