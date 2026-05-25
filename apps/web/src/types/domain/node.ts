export type UUID = string;
export type ISODateString = string;

export type NodeType = "FOLDER" | "DECK";

export interface BreadcrumbEntry {
  id: UUID;
  name: string;
  type: NodeType;
}

export interface NodeRead {
  id: UUID;
  type: NodeType;
  name: string;
  description: string | null;
  parent_node_id: UUID | null;
  visibility: "PRIVATE" | "PUBLIC";
  definition_count: number;
  is_starred: boolean;
  is_pinned: boolean;
  created_at: ISODateString;
  updated_at: ISODateString;
  breadcrumb: BreadcrumbEntry[];
}

export interface NodeCreate {
  type: NodeType;
  name: string;
  description?: string | null;
  parent_node_id?: UUID | null;
}

export interface NodeUpdate {
  name?: string;
  description?: string | null;
}
