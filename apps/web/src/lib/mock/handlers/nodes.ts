// Mock handlers for /nodes* — mirrors apps/api/pycil/hierarchy/router.py.

import { getState, commit } from "../store";
import { newUuid } from "../id";
import type { BreadcrumbEntry, StoreNode } from "../types";
import type { NodeRead, NodeCreate, NodeUpdate } from "@/types/domain";

function nowIso(): string {
  return new Date().toISOString();
}

function definitionCount(deckId: string): number {
  const { terms } = getState();
  return Object.values(terms).filter((t) => t.deck_id === deckId).length;
}

function buildBreadcrumb(node: StoreNode): BreadcrumbEntry[] {
  const { nodes } = getState();
  const chain: BreadcrumbEntry[] = [];
  let current: StoreNode | undefined = node;
  while (current) {
    chain.unshift({ id: current.id, name: current.name, type: current.type });
    current = current.parent_node_id
      ? nodes[current.parent_node_id]
      : undefined;
  }
  return chain;
}

export function toNodeRead(node: StoreNode): NodeRead {
  return {
    id: node.id,
    type: node.type,
    name: node.name,
    description: node.description,
    parent_node_id: node.parent_node_id,
    target_node_id: node.target_node_id ?? null,
    visibility: node.visibility,
    definition_count:
      node.type === "DECK" ? definitionCount(node.id) : 0,
    is_starred: node.is_starred,
    is_pinned: node.is_pinned,
    created_at: node.created_at,
    updated_at: node.updated_at,
    breadcrumb: buildBreadcrumb(node),
  };
}

export function listRootNodes(): NodeRead[] {
  const { nodes } = getState();
  return Object.values(nodes)
    .filter((n) => n.parent_node_id === null)
    .map(toNodeRead);
}

export function getNode(id: string): NodeRead {
  const { nodes } = getState();
  const node = nodes[id];
  if (!node) throw notFound();
  return toNodeRead(node);
}

export function listNodeChildren(id: string): NodeRead[] {
  const { nodes } = getState();
  return Object.values(nodes)
    .filter((n) => n.parent_node_id === id)
    .map(toNodeRead);
}

export function createNode(body: NodeCreate): NodeRead {
  const state = getState();
  const id = newUuid();
  const ts = nowIso();
  const node: StoreNode = {
    id,
    type: body.type,
    name: body.name,
    description: body.description ?? null,
    parent_node_id: body.parent_node_id ?? null,
    visibility: "PRIVATE",
    is_starred: false,
    is_pinned: false,
    created_at: ts,
    updated_at: ts,
  };
  state.nodes[id] = node;
  commit();
  return toNodeRead(node);
}

export function updateNode(id: string, body: NodeUpdate): NodeRead {
  const state = getState();
  const node = state.nodes[id];
  if (!node) throw notFound();
  if (body.name !== undefined && body.name !== null) node.name = body.name;
  if (body.description !== undefined) node.description = body.description;
  node.updated_at = nowIso();
  commit();
  return toNodeRead(node);
}

export function deleteNode(id: string): void {
  const state = getState();
  if (!state.nodes[id]) throw notFound();
  // cascade: remove descendant nodes + their terms
  const toRemove = new Set<string>([id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const n of Object.values(state.nodes)) {
      if (n.parent_node_id && toRemove.has(n.parent_node_id) && !toRemove.has(n.id)) {
        toRemove.add(n.id);
        grew = true;
      }
    }
  }
  for (const nid of toRemove) delete state.nodes[nid];
  for (const t of Object.values(state.terms)) {
    if (toRemove.has(t.deck_id)) delete state.terms[t.id];
  }
  commit();
}

export function toggleStar(id: string): NodeRead {
  const state = getState();
  const node = state.nodes[id];
  if (!node) throw notFound();
  node.is_starred = !node.is_starred;
  node.updated_at = nowIso();
  commit();
  return toNodeRead(node);
}

export function togglePin(id: string): NodeRead {
  const state = getState();
  const node = state.nodes[id];
  if (!node) throw notFound();
  node.is_pinned = !node.is_pinned;
  node.updated_at = nowIso();
  commit();
  return toNodeRead(node);
}

function notFound(): Error {
  return Object.assign(new Error("node_not_found"), { __status: 404 });
}
