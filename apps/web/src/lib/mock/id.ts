// Mock-only id generators. App-runtime (client) use; not used when mock is off.

export function newUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

let intSeed = 0;
export function seedIntCounter(start: number): void {
  intSeed = Math.max(intSeed, start);
}
export function nextInt(): number {
  intSeed += 1;
  return intSeed;
}
export function peekInt(): number {
  return intSeed;
}
