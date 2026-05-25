/** Server actions for nodes — invoked from forms in dashboard pages. */
"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { api } from "@/lib/api";
import type { NodeCreate, NodeRead, NodeType } from "@/lib/types";

export async function createNodeAction(formData: FormData) {
  const type = formData.get("type") as NodeType;
  const name = String(formData.get("name") ?? "").trim();
  const parent_node_id = (formData.get("parent_node_id") as string) || null;
  if (!name) return;
  const payload: NodeCreate = { type, name, parent_node_id };
  const node = await api<NodeRead>("/nodes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  revalidatePath("/dashboard");
  if (parent_node_id) revalidatePath(`/dashboard/${parent_node_id}`);
  redirect(`/dashboard/${node.id}`);
}

export async function deleteNodeAction(nodeId: string, parentId: string | null) {
  await api(`/nodes/${nodeId}`, { method: "DELETE" });
  if (parentId) {
    revalidatePath(`/dashboard/${parentId}`);
    redirect(`/dashboard/${parentId}`);
  }
  revalidatePath("/dashboard");
  redirect("/dashboard");
}

export async function toggleStarAction(nodeId: string) {
  await api<NodeRead>(`/nodes/${nodeId}/star`, { method: "POST" });
  revalidatePath("/dashboard");
  revalidatePath(`/dashboard/${nodeId}`);
}

export async function togglePinAction(nodeId: string) {
  await api<NodeRead>(`/nodes/${nodeId}/pin`, { method: "POST" });
  revalidatePath("/dashboard");
  revalidatePath(`/dashboard/${nodeId}`);
}

export async function addTermAction(deckId: string, formData: FormData) {
  const value = String(formData.get("value") ?? "").trim();
  if (!value) return;
  await api(`/decks/${deckId}/terms`, {
    method: "POST",
    body: JSON.stringify({ value }),
  });
  revalidatePath(`/dashboard/${deckId}`);
}

export async function ensureOnboardingSeed(): Promise<boolean> {
  const r = await api<{ seeded: boolean }>("/onboarding/seed", {
    method: "POST",
  });
  return r.seeded;
}
