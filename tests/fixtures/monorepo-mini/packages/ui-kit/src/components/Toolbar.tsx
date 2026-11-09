import type { ReactNode } from "react";

export interface ToolbarProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  children?: ReactNode;
}

export function Toolbar({ onZoomIn, onZoomOut, children }: ToolbarProps) {
  return (
    <header className="toolbar">
      <button type="button" className="toolbar__button" aria-label="Zoom in" onClick={onZoomIn}>
        +
      </button>
      <button type="button" className="toolbar__button" aria-label="Zoom out" onClick={onZoomOut}>
        −
      </button>
      {children}
    </header>
  );
}
