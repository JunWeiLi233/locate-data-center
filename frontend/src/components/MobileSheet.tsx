import { useEffect, useRef, useState, type PointerEvent, type ReactNode, type CSSProperties } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

export function MobileSheet({ children, className = '', onHeightChange, selectionKey }: { children: ReactNode; className?: string; onHeightChange?: (height: number) => void; selectionKey?: string | null }) {
  const [height, setHeight] = useState(selectionKey ? 48 : 42);
  const lastSelection = useRef(selectionKey ?? null);
  const drag = useRef<{ y: number; height: number } | null>(null);
  useEffect(() => {
    const changed = selectionKey !== lastSelection.current;
    lastSelection.current = selectionKey ?? null;
    if (selectionKey && changed) {
      drag.current = null;
      setHeight(48);
    }
  }, [selectionKey]);
  useEffect(() => { onHeightChange?.(height); }, [height, onHeightChange]);
  const start = (event: PointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('button')) return;
    drag.current = { y: event.clientY, height }; event.currentTarget.setPointerCapture(event.pointerId);
  };
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current) setHeight(Math.min(88, Math.max(18, drag.current.height + (drag.current.y - event.clientY) / window.innerHeight * 100)));
  };
  return <div className={`mobile-sheet ${className}`} style={{ '--sheet-height': `${height}dvh` } as CSSProperties}>
    <div className="sheet-handle" onPointerDown={start} onPointerMove={move} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <span className="sheet-grip" aria-hidden="true" /><div className="sheet-position-buttons"><button className="icon-button" aria-label="Expand bottom sheet" onClick={() => setHeight(88)}><ChevronUp size={16} /></button><button className="text-button" aria-label="Half-height bottom sheet" onClick={() => setHeight(48)}>Half</button><button className="icon-button" aria-label="Minimize bottom sheet" onClick={() => setHeight(18)}><ChevronDown size={16} /></button></div>
    </div><div className="sheet-content">{children}</div>
  </div>;
}
