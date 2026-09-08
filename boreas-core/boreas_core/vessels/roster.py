"""Real, curated roster of Antarctic-programme vessels with genuine, verifiable
public AIS visibility -- not limited to India's NCPOR charters, so the roster
is broad enough to plausibly show a real live AIS fix during an actual port
call (Cape Town, Hobart, Punta Arenas, Bremerhaven, St Petersburg, Shanghai
all have real terrestrial AIS coverage).

Every field below is either independently verifiable (IMO/MMSI registries,
NCPOR/press reporting, operator/agency press releases) or explicitly marked
`None` rather than guessed. Do not add a vessel here without a citation in
its own comment -- that is the whole point of this module existing instead
of free-text vessel entry in the UI (BOREAS design doc: "guarantees only
real, existing vessels can be selected").

Two vessels below (Laurence M. Gould, Nathaniel B. Palmer) are real but no
longer in active Antarctic service as of this writing -- kept in the roster
with `active=False` rather than dropped, since "the US Antarctic Program
currently operates no dedicated vessel of its own" is itself a real,
verifiable, and notable fact, not something to quietly omit. The frontend's
voyage planner only offers `active=True` vessels for selection.
"""

from dataclasses import dataclass

# Home port coordinates are well-known city/port locations (same confidence
# level as CAPE_TOWN_PORT below), not independently fact-checked beyond that.
CAPE_TOWN_PORT = (18.4231, -33.9022)  # Port of Cape Town, South Africa
HOBART_PORT = (147.3272, -42.8821)  # Hobart, Tasmania -- RSV Nuyina's home port
BREMERHAVEN_PORT = (8.5809, 53.5396)  # Bremerhaven, Germany -- AWI's home port
ST_PETERSBURG_PORT = (30.3141, 59.9343)  # St Petersburg, Russia -- AARI's home port
SHANGHAI_PORT = (121.4737, 31.2304)  # Shanghai, China -- PRIC's home port
PUNTA_ARENAS_PORT = (-70.9171, -53.1638)  # Punta Arenas, Chile -- USAP Antarctic Peninsula staging port
STANLEY_FALKLANDS_PORT = (-57.8500, -51.7000)  # Stanley, Falkland Islands -- RRS SDA's flag port


@dataclass(frozen=True)
class RosterVessel:
    id: str
    name: str
    imo: str | None
    mmsi: str | None
    vessel_type: str
    ice_class_note: str
    home_port: str
    home_port_lonlat: tuple[float, float]
    assigned_station_ids: tuple[str, ...]
    active: bool
    source_note: str


ROSTER: tuple[RosterVessel, ...] = (
    RosterVessel(
        id="vasiliy_golovnin",
        name="MV Vasiliy Golovnin",
        # IMO/MMSI confirmed via VesselFinder and MarineTraffic. NOTE: a
        # different ship (a fish factory vessel) also carries this name
        # under IMO 8913277 -- this is the icebreaking cargo ship, not that
        # one.
        imo="8723426",
        mmsi="273149510",
        vessel_type="Project 10620 icebreaking general cargo ship",
        ice_class_note="Ice-strengthened cargo vessel, built 1988 (Kherson, Ukrainian SSR); operated by FESCO (Far Eastern Shipping Company), Russia.",
        home_port="Cape Town, South Africa",
        home_port_lonlat=CAPE_TOWN_PORT,
        assigned_station_ids=("bharati", "maitri"),
        active=True,
        source_note=(
            "IMO/MMSI: vesselfinder.com/vessels/details/8723426, "
            "marinetraffic.com (mmsi:273149510). Charter: FESCO-NCPOR contract "
            "(Oct 2021) covering both stations across five austral seasons "
            "through 2026 -- polarjournal.ch/en/2024/03/25, pib.gov.in "
            "PRID=1685978, marinelink.com/news/470440."
        ),
    ),
    RosterVessel(
        id="ivan_papanin",
        name="MV Ivan Papanin",
        # IMO/MMSI confirmed via VesselFinder/vesseltracker. NOTE: a
        # different, newer Russian Navy patrol ship (Project 23550,
        # commissioned 2025, IMO 9898151) also carries this name -- this is
        # the 1990-built cargo vessel, not that one.
        imo="8837928",
        mmsi="273137200",
        vessel_type="Ice-strengthened general cargo ship",
        ice_class_note="Built 1990, Russia-flagged, ice-strengthened hull; used for NCPOR expeditions for multiple seasons.",
        home_port="Cape Town, South Africa",
        home_port_lonlat=CAPE_TOWN_PORT,
        assigned_station_ids=("bharati",),
        active=True,
        source_note=(
            "IMO/MMSI: vesselfinder.com/vessels/IVAN-PAPANIN-IMO-8837928-MMSI-273137200, "
            "vesseltracker.com/en/Ships/Ivan-Papanin-8837928.html. Bharati "
            "service confirmed directly by NCPOR's own incident report "
            "(ballast-tank water ingress shortly after departing Bharati for "
            "Maitri, 5 Feb 2018): ncpor.res.in/news/view/414."
        ),
    ),
    RosterVessel(
        id="sir_david_attenborough",
        name="RRS Sir David Attenborough",
        imo="9798222",
        mmsi="740405000",
        vessel_type="Polar research and logistics vessel",
        ice_class_note="Commissioned 2021, Polar Class PC5-equivalent icebreaking hull; operated by British Antarctic Survey, flagged Falkland Islands.",
        home_port="Stanley, Falkland Islands",
        home_port_lonlat=STANLEY_FALKLANDS_PORT,
        assigned_station_ids=(),
        active=True,
        source_note=(
            "IMO/MMSI: marinetraffic.com (shipid:6308260, mmsi:740405000, "
            "imo:9798222), vesselfinder.com/vessels/details/9798222, "
            "en.wikipedia.org/wiki/RRS_Sir_David_Attenborough. Resupplies BAS "
            "stations (Rothera etc.), not Bharati/Maitri -- no assigned "
            "station overlap with this app's checkpoint list."
        ),
    ),
    RosterVessel(
        id="nuyina",
        name="RSV Nuyina",
        imo="9797060",
        mmsi="503000183",
        vessel_type="Icebreaking research and resupply vessel",
        ice_class_note="Delivered 2021, replaced Aurora Australis; operated by Serco Defence for the Australian Antarctic Division.",
        home_port="Hobart, Tasmania, Australia",
        home_port_lonlat=HOBART_PORT,
        assigned_station_ids=(),
        active=True,
        source_note=(
            "IMO/MMSI: en.wikipedia.org/wiki/RSV_Nuyina, "
            "vesselfinder.com/vessels/details/9797060, "
            "vesseltracker.com/en/Ships/Nuyina-9797060.html, "
            "antarctica.gov.au/nuyina. Resupplies Casey/Davis/Mawson and "
            "Macquarie Island -- not Bharati/Maitri."
        ),
    ),
    RosterVessel(
        id="polarstern",
        name="Polarstern",
        imo="8013132",
        mmsi="211202460",
        vessel_type="Icebreaking research vessel",
        ice_class_note="Commissioned 1982, operates in both Arctic and Antarctic (e.g. MOSAiC expedition); operated by the Alfred Wegener Institute (AWI), Germany.",
        home_port="Bremerhaven, Germany",
        home_port_lonlat=BREMERHAVEN_PORT,
        # AWI, Polarstern's operator, also operates Neumayer Station III --
        # a real, verifiable institutional link (not a resupply-contract
        # citation like the Indian vessels above, but a genuine same-agency
        # connection worth surfacing).
        assigned_station_ids=("neumayer_iii",),
        active=True,
        source_note=(
            "IMO/MMSI: vesselfinder.com/vessels/details/8013132 (confirmed "
            "flag Germany), awi.de/en/fleet-stations, "
            "en.wikipedia.org/wiki/RV_Polarstern."
        ),
    ),
    RosterVessel(
        id="akademik_fedorov",
        name="Akademik Fedorov",
        imo="8519837",
        mmsi="273412710",
        vessel_type="Icebreaker / research-supply vessel",
        ice_class_note="Built 1987; operated by the Arctic and Antarctic Research Institute (AARI) for the Russian Antarctic Expedition.",
        home_port="St Petersburg, Russia",
        home_port_lonlat=ST_PETERSBURG_PORT,
        assigned_station_ids=(),
        active=True,
        source_note=(
            "IMO/MMSI: en.wikipedia.org/wiki/Akademik_Fedorov, "
            "myshiptracking.com/vessels/akademik-fedorov-mmsi-273412710-imo-8519837, "
            "vesseltracker.com/en/Ships/Akademik-Fedorov-8519837.html. Active "
            "as of Nov 2025 (en route St Petersburg -> Cape Town per "
            "vesseltracker); delivered the 70th RAE to Mirny Feb 2025 -- "
            "tass.com/society/1909749. Resupplies Mirny, not Bharati/Maitri."
        ),
    ),
    RosterVessel(
        id="xue_long_2",
        name="Xue Long 2",
        # NOTE: a distinct, older ship "Xue Long" (no "2"), IMO 8877899,
        # also exists -- do not conflate. This entry is the newer vessel.
        imo="9829241",
        mmsi="413381260",
        vessel_type="Polar icebreaker",
        ice_class_note="Entered service July 2019; operated by the Polar Research Institute of China.",
        home_port="Shanghai, China",
        home_port_lonlat=SHANGHAI_PORT,
        assigned_station_ids=(),
        active=True,
        source_note=(
            "IMO/MMSI: marinetraffic.com (shipid:5869480, mmsi:413381260, "
            "imo:9829241), vesselfinder.com/vessels/details/9829241, "
            "en.wikipedia.org/wiki/Xue_Long_2. Resupplies Zhongshan/Great "
            "Wall/Kunlun/Taishan, not Bharati/Maitri."
        ),
    ),
    RosterVessel(
        id="laurence_m_gould",
        name="Laurence M. Gould",
        imo="9137337",
        mmsi="368138000",
        vessel_type="Research and resupply vessel",
        ice_class_note="Operated by Edison Chouest Offshore under the US Antarctic Support Contract for NSF; shuttled Punta Arenas <-> Palmer Station.",
        home_port="Punta Arenas, Chile",
        home_port_lonlat=PUNTA_ARENAS_PORT,
        assigned_station_ids=(),
        active=False,
        source_note=(
            "IMO/MMSI: en.wikipedia.org/wiki/RV_Laurence_M._Gould, "
            "marinetraffic.com (shipid:454309, mmsi:368138000, imo:9137337). "
            "INACTIVE: NSF's Edison Chouest charter expired 16 Jul 2024 and "
            "was not renewed (nsf.gov/geo/opp/updates/future-plans-usap-"
            "vessel-support-arsv-laurence-m-gould) -- kept in the roster as "
            "a real, verifiable fact about the current state of Antarctic "
            "logistics, not as a plannable vessel."
        ),
    ),
    RosterVessel(
        id="nathaniel_b_palmer",
        name="Nathaniel B. Palmer",
        imo="9007257",
        mmsi="366610000",
        vessel_type="Icebreaking research vessel",
        ice_class_note="In USAP service since 1992 under the Antarctic Support Contract for NSF, homeported Punta Arenas.",
        home_port="Punta Arenas, Chile",
        home_port_lonlat=PUNTA_ARENAS_PORT,
        assigned_station_ids=(),
        active=False,
        source_note=(
            "IMO/MMSI: en.wikipedia.org/wiki/Nathaniel_B._Palmer_(icebreaker), "
            "marinetraffic.com (shipid:426075, mmsi:366610000, imo:9007257). "
            "INACTIVE: NSF's own official update (nsf.gov/od/opp/updates/"
            "update-nathaniel-b-palmer) confirms the charter was terminated "
            "for budget reasons after a final cruise in Oct 2025, leaving "
            "USAP without a dedicated research icebreaker -- a real, "
            "notable fact kept visible rather than silently dropped."
        ),
    ),
)


def get_vessel_by_id(vessel_id: str) -> RosterVessel | None:
    return next((v for v in ROSTER if v.id == vessel_id), None)
