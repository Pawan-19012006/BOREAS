// BOREAS SHIP -- the Captain's bridge terminal.
//
// One vessel, one active route, one decision to make when Shore proposes a
// change. Reads the same boreas-core backend as the Shore application via
// simple polling (see hooks/useShipSession.ts) -- no separate routing
// engine, no fabricated geometry, no websockets.

import { useEffect, useState } from 'react';
import ShipGlobe from './components/ShipGlobe';
import MissionHud from './components/MissionHud';
import RouteUpdateAlert from './components/RouteUpdateAlert';
import VesselSelector from './components/VesselSelector';
import { useShipSession } from './hooks/useShipSession';
import { getRoster, type RosterVessel } from './services/api';
import './styles.css';

function App() {
  const [roster, setRoster] = useState<RosterVessel[]>([]);
  const [isRosterLoading, setIsRosterLoading] = useState(true);
  const [vesselId, setVesselId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRoster().then((v) => {
      if (!cancelled) {
        setRoster(v);
        setIsRosterLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const session = useShipSession(vesselId);
  const vesselName = roster.find((v) => v.id === vesselId)?.name ?? vesselId ?? 'Vessel';

  if (!vesselId) {
    return <VesselSelector roster={roster} isLoading={isRosterLoading} onSelect={setVesselId} />;
  }

  return (
    <div className="ship-app-root">
      <ShipGlobe
        route={session.activeRoute?.route ?? null}
        vesselState={session.vesselState}
        destinationName={session.missionInfo?.destination_name ?? null}
      />

      <header className="ship-top-bar">
        <span className="brand-mark">BOREAS SHIP</span>
        <button type="button" className="btn-link" onClick={() => setVesselId(null)}>
          Change vessel
        </button>
      </header>

      {session.isWaitingForShore && (
        <div className="waiting-banner">
          <p>
            <strong>{vesselName}</strong> has no active route yet. Waiting for Shore to start
            monitoring and assign one&hellip;
          </p>
        </div>
      )}

      {session.activeRoute && session.vesselState && (
        <MissionHud
          vesselName={vesselName}
          missionInfo={session.missionInfo}
          activeRoute={session.activeRoute}
          vesselState={session.vesselState}
        />
      )}

      {session.lastResolved && !session.pendingUpdate && (
        <div className={`resolution-banner ${session.lastResolved.status === 'ACCEPTED' ? 'accepted' : 'declined'}`}>
          <span>
            Route update {session.lastResolved.status === 'ACCEPTED' ? 'accepted — now on the new route.' : 'declined — remaining on the current route.'}
          </span>
          <button type="button" className="btn-link" onClick={session.dismissResolution}>
            Dismiss
          </button>
        </div>
      )}

      {session.pendingUpdate && (
        <RouteUpdateAlert
          update={session.pendingUpdate}
          isDeciding={session.isDeciding}
          error={session.decisionError}
          onDecide={session.decide}
        />
      )}
    </div>
  );
}

export default App;
