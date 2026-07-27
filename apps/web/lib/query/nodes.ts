import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  NodeCreateRequest,
  NodeItem,
  NodeMoveRequest,
  NodePageResponse,
  NodeUpdateRequest,
  NodeVisibilityRequest,
} from "@/lib/api/types";
import { queryKeys } from "./keys";

async function fetchNodes(parentNodeId?: string | null): Promise<NodePageResponse> {
  const url = parentNodeId
    ? `/api/nodes?parentNodeId=${encodeURIComponent(parentNodeId)}`
    : "/api/nodes";
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error("Failed to fetch nodes");
  }
  return res.json();
}

async function fetchNode(id: string): Promise<NodeItem> {
  const res = await fetch(`/api/nodes/${id}`);
  if (!res.ok) {
    throw new Error("Failed to fetch node details");
  }
  return res.json();
}

export function useNodes(parentNodeId?: string | null) {
  return useQuery({
    queryKey: queryKeys.nodes.list(parentNodeId || undefined),
    queryFn: () => fetchNodes(parentNodeId),
  });
}

export function useNodeDetail(id: string) {
  return useQuery({
    queryKey: queryKeys.nodes.detail(id),
    queryFn: () => fetchNode(id),
    enabled: !!id,
  });
}

export function useCreateNode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: NodeCreateRequest): Promise<NodeItem> => {
      const res = await fetch("/api/nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error?.error?.message || "Failed to create node");
      }
      return res.json();
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.nodes.list(variables.parentNodeId || undefined),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.nodes.all,
      });
    },
  });
}

export function useUpdateNode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: NodeUpdateRequest }): Promise<NodeItem> => {
      const res = await fetch(`/api/nodes/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error?.error?.message || "Failed to update node");
      }
      return res.json();
    },
    onSuccess: (updatedNode) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.detail(updatedNode.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.all });
    },
  });
}

export function useMoveNode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: NodeMoveRequest }): Promise<NodeItem> => {
      const res = await fetch(`/api/nodes/${id}/move`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error?.error?.message || "Failed to move node");
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.all });
    },
  });
}

export function useUpdateNodeVisibility() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: NodeVisibilityRequest }): Promise<NodeItem> => {
      const res = await fetch(`/api/nodes/${id}/visibility`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error?.error?.message || "Failed to update visibility");
      }
      return res.json();
    },
    onSuccess: (updatedNode) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.detail(updatedNode.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.all });
    },
  });
}

export function useDeleteNode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      const res = await fetch(`/api/nodes/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error?.error?.message || "Failed to delete node");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.all });
    },
  });
}
