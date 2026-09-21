// Safe lifecycle for a Cesium CustomDataSource inside a React effect.
//
// `viewer.dataSources.add()` is ASYNCHRONOUS -- it returns a Promise. A naive
//
//     const s = new CustomDataSource(name);
//     viewer.dataSources.add(s);
//     return () => viewer.dataSources.remove(s, true);
//
// leaks the source whenever the effect tears down before that promise settles:
// `remove` finds nothing to remove, the pending `add` then completes, and the
// orphan stays on the globe forever. React StrictMode double-invokes effects,
// so in development this happens on literally every mount, leaving two copies
// of every layer -- including stale ones drawn with superseded props.
//
// This helper makes the teardown await the add, so a source is always removed
// no matter which order the two resolve in.

import { useEffect, type MutableRefObject } from 'react';
import { CustomDataSource, type Viewer } from 'cesium';

/**
 * Creates a CustomDataSource, hands it to `populate` to fill with entities,
 * and guarantees its removal on cleanup.
 *
 * @param viewer   The Cesium viewer to attach to.
 * @param name     Data source name, for debugging.
 * @param populate Fills the source. Runs before the source is attached, which
 *                 Cesium allows and which avoids a visible empty frame.
 * @param deps     Effect dependencies; the source is rebuilt when they change.
 * @param sourceRef Optional out-param, for layers that update entities on a
 *                  tick rather than rebuilding the whole source.
 */
export function useCesiumDataSource(
  viewer: Viewer,
  name: string,
  populate: (source: CustomDataSource) => void,
  deps: React.DependencyList,
  sourceRef?: MutableRefObject<CustomDataSource | null>,
): void {
  useEffect(() => {
    const source = new CustomDataSource(name);
    let disposed = false;

    populate(source);

    const detach = () => {
      if (!viewer.isDestroyed()) {
        viewer.dataSources.remove(source, true);
      }
    };

    // If teardown already happened by the time the add resolves, remove it now.
    void viewer.dataSources.add(source).then(() => {
      if (disposed) {
        detach();
        return;
      }
      if (sourceRef) sourceRef.current = source;
    });

    return () => {
      disposed = true;
      if (sourceRef && sourceRef.current === source) sourceRef.current = null;
      detach();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
