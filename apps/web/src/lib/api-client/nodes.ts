import { fetchJson } from "./base";
import type { NodeCreate, NodeRead, NodeUpdate, UUID } from "@/types/domain";

export function listRootNodes() {
  return fetchJson<NodeRead[]>("/nodes/root");
}

export function getNode(id: UUID) {
  return fetchJson<NodeRead>(`/nodes/${id}`);
}

export function listNodeChildren(id: UUID) {
  return fetchJson<NodeRead[]>(`/nodes/${id}/children`);
}

export function createNode(body: NodeCreate) {
  return fetchJson<NodeRead>("/nodes", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateNode(id: UUID, body: NodeUpdate) {
  return fetchJson<NodeRead>(`/nodes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteNode(id: UUID) {
  return fetchJson<void>(`/nodes/${id}`, { method: "DELETE" });
}

export function toggleStar(id: UUID) {
  return fetchJson<NodeRead>(`/nodes/${id}/star`, { method: "POST" });
}

export function togglePin(id: UUID) {
  return fetchJson<NodeRead>(`/nodes/${id}/pin`, { method: "POST" });
}
