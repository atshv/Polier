import type { CanvasHandle } from "@canvas/engine";
import type { CanvasState } from "@canvas/sync";
import { Stage, Toolbar } from "@canvas/ui-kit";

export const metadata = {
  title: "canvas-mini",
};

// The app is the only place that wires engine, kit and service (P-1).
export default function Page() {
  const handle: CanvasHandle | null = null;
  const state: CanvasState | null = null;
  const zoom = state === null ? 1 : state.viewport.zoom;

  return (
    <main className="app">
      <Toolbar onZoomIn={() => undefined} onZoomOut={() => undefined} />
      <Stage handle={handle} zoom={zoom} />
    </main>
  );
}
