// Real Antarctic research station coordinates (India's two active stations),
// used as selectable navigation destinations. Sourced from Wikipedia/geodesy
// references: Bharati 69°24'29"S 76°11'14"E, Maitri 70°46'00"S 11°43'55"E.
// Kept frontend-only: the routing backend only ever needs plain goal_lon/
// goal_lat floats (see services/boreasApi.ts) and has no reason to know
// station *names*, matching how missionData.ts already keeps iceberg/vessel
// names client-side.

export interface AntarcticCheckpoint {
  id: string;
  name: string;
  lon: number;
  lat: number;
  operator: string;
  description: string;
}

export const ANTARCTIC_CHECKPOINTS: AntarcticCheckpoint[] = [
  {
    id: 'bharati',
    name: 'Bharati Station',
    lon: 76.187361,
    lat: -69.408030,
    operator: 'NCPOR / India',
    description: 'India’s third Antarctic station, Larsemann Hills, Prydz Bay. Established 2012.',
  },
  {
    id: 'maitri',
    name: 'Maitri Station',
    lon: 11.731944,
    lat: -70.766667,
    operator: 'NCPOR / India',
    description: 'India’s second Antarctic station, Schirmacher Hills, Queen Maud Land. Established 1989.',
  },
  {
    id: 'novolazarevskaya',
    name: 'Novolazarevskaya Station',
    lon: 11.823889,
    lat: -70.776944,
    operator: 'AARI / Russia',
    description: 'Russian year-round station at Schirmacher Oasis, Queen Maud Land -- opened 1961, ~75km from the coast, close to Maitri.',
  },
  {
    id: 'sanae_iv',
    name: 'SANAE IV',
    lon: -2.828611,
    lat: -71.673611,
    operator: 'South African National Antarctic Programme',
    description: 'South Africa’s Antarctic research base at Vesleskarvet, Queen Maud Land -- established 1997, elevation 850m.',
  },
  {
    id: 'neumayer_iii',
    name: 'Neumayer Station III',
    lon: -8.274167,
    lat: -70.674444,
    operator: 'Alfred Wegener Institute / Germany',
    description: 'German year-round station on the Ekström Ice Shelf, Queen Maud Land, operated by AWI since 2009.',
  },
  {
    id: 'syowa',
    name: 'Syowa Station',
    lon: 39.581836,
    lat: -69.004122,
    operator: 'National Institute of Polar Research / Japan',
    description: 'Japan’s main Antarctic research station on East Ongul Island, Queen Maud Land -- established 1957.',
  },
];

export function getCheckpointById(id: string): AntarcticCheckpoint | undefined {
  return ANTARCTIC_CHECKPOINTS.find((c) => c.id === id);
}
