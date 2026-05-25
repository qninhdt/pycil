"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import * as nodesApi from "@/lib/api-client/nodes";
import { queryKeys } from "@/lib/api-client/query-keys";
import type { NodeCreate, NodeUpdate, UUID } from "@/types/domain";

export function useRootNodes() {
  return useQuery({
    queryKey: queryKeys.nodes.root(),
    queryFn: nodesApi.listRootNodes,
  });
}

export function useNode(id: UUID | undefined) {
  return useQuery({
    queryKey: id ? queryKeys.nodes.detail(id) : queryKeys.nodes.detail("__none"),
    queryFn: () => nodesApi.getNode(id as UUID),
    enabled: !!id,
  });
}

export function useNodeChildren(id: UUID | undefined) {
  return useQuery({
    queryKey: id
      ? queryKeys.nodes.children(id)
      : queryKeys.nodes.children("__none"),
    queryFn: () => nodesApi.listNodeChildren(id as UUID),
    enabled: !!id,
  });
}

export function useCreateNode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NodeCreate) => nodesApi.createNode(body),
    onSuccess: (_node, body) => {
      qc.invalidateQueries({ queryKey: queryKeys.nodes.root() });
      if (body.parent_node_id) {
        qc.invalidateQueries({
          queryKey: queryKeys.nodes.children(body.parent_node_id),
        });
      }
    },
  });
}

export function useUpdateNode(id: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: NodeUpdate) => nodesApi.updateNode(id, body),
    onSuccess: (node) => {
      qc.invalidateQueries({ queryKey: queryKeys.nodes.detail(id) });
      if (node.parent_node_id) {
        qc.invalidateQueries({
          queryKey: queryKeys.nodes.children(node.parent_node_id),
        });
      }
      qc.invalidateQueries({ queryKey: queryKeys.nodes.root() });
    },
  });
}

export function useDeleteNode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: UUID) => nodesApi.deleteNode(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.nodes.all() });
    },
  });
}

export function useToggleStar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: UUID) => nodesApi.toggleStar(id),
    onSuccess: (node) => {
      qc.invalidateQueries({ queryKey: queryKeys.nodes.detail(node.id) });
      qc.invalidateQueries({ queryKey: queryKeys.nodes.root() });
    },
  });
}

export function useTogglePin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: UUID) => nodesApi.togglePin(id),
    onSuccess: (node) => {
      qc.invalidateQueries({ queryKey: queryKeys.nodes.detail(node.id) });
      qc.invalidateQueries({ queryKey: queryKeys.nodes.root() });
    },
  });
}
