/**
 * Turning a missed union member into a compile error.
 *
 * The assistant's event union is a wire contract: the API can grow a new event type,
 * and every place that switches on `eventType` has to be revisited when it does. A
 * plain `switch` does not enforce that. Without a `default` arm the compiler is happy
 * for a case to be missing, so a new event is silently dropped — the transcript just
 * renders one fewer thing, with nothing to debug and no failing check.
 *
 * Calling this in the `default` arm fixes that. The parameter is `never`, so it type
 * checks only while the switch is exhaustive; the moment a member is added, the
 * narrowed value is no longer `never` and the call fails to compile at every switch
 * that needs updating.
 *
 * It also throws at runtime rather than returning, because reaching it means the
 * running build received an event a newer API invented. Where that is expected —
 * parsing untrusted frames off the wire — the caller checks membership first instead
 * of relying on this.
 */
export function assertNever(value: never, context: string): never {
  throw new Error(`${context}: unhandled variant ${JSON.stringify(value)}`)
}
