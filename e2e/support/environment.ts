import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { loadEnvFile } from "node:process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const root = fileURLToPath(new URL("../../", import.meta.url));
export const directory = resolve(root, "e2e");
const envFile = process.env.E2E_ENV_FILE ?? resolve(directory, ".env");
if (process.env.E2E_ENV_FILE || existsSync(envFile)) loadEnvFile(envFile);

export const runId = process.env.E2E_RUN_ID ?? randomUUID().replaceAll("-", "");
if (!/^[a-z0-9]{12,40}$/.test(runId)) throw new Error("Invalid E2E_RUN_ID");
process.env.E2E_RUN_ID = runId;
export const artifacts = resolve(directory, ".artifacts", runId);
export const webURL = "http://localhost:3200";
export const apiURL = "http://127.0.0.1:8100";
export const providerURL = "http://127.0.0.1:8110";

export function credentials(live: boolean): Record<string, string> {
  const names = [
    "CLERK_SECRET_KEY",
    "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
    "CLERK_ISSUER",
    "CLERK_JWKS_URL",
  ];
  if (live)
    names.push(
      "LLM_API_KEY",
      "LLM_BASE_URL",
      "DECISION_API_KEY",
      "DECISION_BASE_URL",
    );
  const missing = names.filter((name) => !process.env[name]?.trim());
  if (missing.length)
    throw new Error(`Missing E2E variables: ${missing.join(", ")}`);
  if (
    !process.env.CLERK_SECRET_KEY!.startsWith("sk_test_") ||
    !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY!.startsWith("pk_test_")
  ) {
    throw new Error("E2E requires Clerk development keys");
  }
  const issuer = new URL(process.env.CLERK_ISSUER!);
  const jwks = new URL(process.env.CLERK_JWKS_URL!);
  const publishedHost = Buffer.from(
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY!.slice(8),
    "base64",
  )
    .toString()
    .replace(/\$$/, "");
  if (
    issuer.protocol !== "https:" ||
    jwks.origin !== issuer.origin ||
    publishedHost !== issuer.host
  ) {
    throw new Error(
      "Clerk issuer, JWKS and publishable key must identify the same development instance",
    );
  }
  return Object.fromEntries(names.map((name) => [name, process.env[name]!]));
}

export function frontendEnvironment(): Record<string, string> {
  return {
    E2E_RUN_ID: runId,
    E2E_ARTIFACTS: artifacts,
    NEXT_PUBLIC_DATA_MODE: "live",
    NEXT_PUBLIC_PYCIL_API_URL: apiURL,
    PYCIL_API_URL: apiURL,
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY:
      process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "",
    CLERK_SECRET_KEY: process.env.CLERK_SECRET_KEY ?? "",
  };
}
