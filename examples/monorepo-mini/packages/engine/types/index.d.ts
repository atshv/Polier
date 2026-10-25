export interface NodeSnapshot {
  id: number;
  type: "rect" | "ellipse" | "text" | "frame";
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
}

export interface CanvasHandle {
  nodeCount(): number;
  hitTest(x: number, y: number): number | null;
  contractVersion(): string;
}

export declare const engineVersion: string;
