import type { CanvasHandle } from "@canvas/engine";

export interface StageProps {
  handle: CanvasHandle | null;
  zoom: number;
}

// The stage is a thin shell: the engine draws, the kit only positions it (P-3).
export function Stage({ handle, zoom }: StageProps) {
  const count = handle === null ? 0 : handle.nodeCount();
  return (
    <section className="stage" aria-label="Canvas stage" data-zoom={zoom}>
      <p className="stage__count">{count} nodes</p>
    </section>
  );
}
