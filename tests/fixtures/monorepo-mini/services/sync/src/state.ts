// Mirrors contracts/state/state.schema.json version 1.0.0. A field changes here
// only in the same task as the contract version (ADR-0002).
export interface NodeState {
  id: string;
  type: "rect" | "ellipse" | "text" | "frame";
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
}

export interface EdgeState {
  from: string;
  to: string;
  label?: string;
}

export interface ViewportState {
  x: number;
  y: number;
  zoom: number;
}

export interface CanvasState {
  contract: "state";
  version: "1.0.0";
  documentId: string;
  nodes: NodeState[];
  edges: EdgeState[];
  viewport: ViewportState;
  updatedAt: string;
}

export const CONTRACT_VERSION = "1.0.0";

// The same subset the project contract gate validates. Returns one line per problem.
export function validateState(value: unknown): string[] {
  const problems: string[] = [];
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return ["state: expected an object"];
  }
  const state = value as Partial<CanvasState>;
  if (state.contract !== "state") {
    problems.push("state.contract: expected \"state\"");
  }
  if (state.version !== CONTRACT_VERSION) {
    problems.push(`state.version: expected ${CONTRACT_VERSION}, got ${String(state.version)}`);
  }
  if (typeof state.documentId !== "string" || state.documentId.length === 0) {
    problems.push("state.documentId: expected a non-empty string");
  }
  if (!Array.isArray(state.nodes)) {
    problems.push("state.nodes: expected an array");
  }
  if (!Array.isArray(state.edges)) {
    problems.push("state.edges: expected an array");
  }
  if (typeof state.viewport !== "object" || state.viewport === null) {
    problems.push("state.viewport: expected an object");
  } else if (!(state.viewport.zoom > 0)) {
    problems.push("state.viewport.zoom: expected a number greater than 0");
  }
  return problems;
}
