import { ApiError } from "./errors"

export type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string; code: string }

export async function handleAction<T>(fn: () => Promise<T>): Promise<ActionResult<T>> {
  try {
    return { success: true, data: await fn() }
  } catch (error) {
    if (error instanceof ApiError) {
      return { success: false, error: error.message, code: error.code }
    }
    return {
      success: false,
      error: error instanceof Error ? error.message : "An unexpected error occurred",
      code: "unknown",
    }
  }
}
