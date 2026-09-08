import { useEffect, useState } from 'react';
import type { Viewer } from 'cesium';
import type { Selection, SelectionKind } from '../types/selection';

// Entities across all layers are tagged with ids shaped "<kind>:<id>" so a single
// viewer.selectedEntityChanged listener can drive the Inspector dock regardless
// of which CustomDataSource the entity lives in.
export function useSelectedEntity(viewer: Viewer | null): [Selection | null, (s: Selection | null) => void] {
  const [selection, setSelection] = useState<Selection | null>(null);

  useEffect(() => {
    if (!viewer) return;

    const onChange = () => {
      const entity = viewer.selectedEntity;
      if (!entity || typeof entity.id !== 'string' || !entity.id.includes(':')) {
        setSelection(null);
        return;
      }
      const [kind, id] = entity.id.split(':');
      setSelection({ kind: kind as SelectionKind, id });
    };

    viewer.selectedEntityChanged.addEventListener(onChange);
    return () => {
      if (!viewer.isDestroyed()) {
        viewer.selectedEntityChanged.removeEventListener(onChange);
      }
    };
  }, [viewer]);

  return [selection, setSelection];
}
