// Textes de la page publique « écoute » (et de la carte en vue écoute) en FR / EN / ES.
// La langue vient de ?lang= (passée par le bandeau du WebSDR, selon la langue choisie par l'auditeur).
export const PAGE_LANG = (() => {
  try {
    const l = new URLSearchParams(location.search).get('lang');
    return ['fr', 'en', 'es'].includes(l) ? l : 'fr';
  } catch { return 'fr'; }
})();

export const TXT = {
  fr: {
    title: 'WebSDR ORSAT — où le récepteur entend bien en ce moment',
    intro: "Choisissez une bande : la carte montre, depuis le récepteur, les régions d'où les signaux arrivent bien (propagation mesurée par les ionosondes, et diagramme réel de l'antenne). Molette sur la carte pour zoomer.",
    labels: { G: 'bonne écoute', M: 'écoute moyenne', P: 'écoute faible (antenne peu favorable à cet angle)',
              a: 'absorbée (couche D)', c: 'zone de silence (MUF dépassée)', '-': 'pas de mesure' },
    nodata: "pas de mesure (pas d'ionosonde assez proche)",
    hover: "Survolez la carte pour le détail d'une zone.",
    cell: (band, az, r0, r1, label, muf) => `${band} · azimut ${az}° · ${r0}–${r1} km : ${label}${muf ? ` · MUF ${muf} MHz` : ''}`,
    receiver: (loc) => `Récepteur : WebSDR ORSAT (${loc}). Antenne : loop horizontale de 80 m de périmètre à 6 m au-dessus du sol, balun 4:1 (diagramme calculé avec NEC).`,
    how: "Chaque case : la bande passe-t-elle depuis là (ionosondes mesurées), et la loop reçoit-elle bien sous cet angle d'arrivée ?",
    note: (when) => `Projection azimutale équidistante centrée sur le WebSDR : distances et azimuts vrais depuis le récepteur. Molette sur la carte : zoom. Calcul de ${when}. Fond de carte et villes Natural Earth (domaine public).`,
    aria: (band) => `Carte d'écoute ORSAT sur ${band}`,
    loading: 'Calcul de la carte…',
    west: 'O',
  },
  en: {
    title: 'ORSAT WebSDR — where the receiver hears well right now',
    intro: 'Pick a band: the map shows, from the receiver, the regions from which signals come in well (propagation measured by ionosondes, and the real antenna pattern). Mouse wheel on the map to zoom.',
    labels: { G: 'good reception', M: 'fair reception', P: 'weak reception (antenna not favourable at this angle)',
              a: 'absorbed (D layer)', c: 'skip zone (above the MUF)', '-': 'no data' },
    nodata: 'no data (no ionosonde close enough)',
    hover: 'Hover over the map for details of an area.',
    cell: (band, az, r0, r1, label, muf) => `${band} · bearing ${az}° · ${r0}–${r1} km: ${label}${muf ? ` · MUF ${muf} MHz` : ''}`,
    receiver: (loc) => `Receiver: ORSAT WebSDR (${loc}). Antenna: horizontal loop, 80 m perimeter, 6 m above ground, 4:1 balun (pattern computed with NEC).`,
    how: 'Each cell: does the band open from there (measured ionosondes), and does the loop receive well at that arrival angle?',
    note: (when) => `Azimuthal equidistant projection centred on the WebSDR: true distances and bearings from the receiver. Mouse wheel on the map: zoom. Computed at ${when}. Base map and cities: Natural Earth (public domain).`,
    aria: (band) => `ORSAT reception map on ${band}`,
    loading: 'Computing the map…',
    west: 'W',
  },
  es: {
    title: 'WebSDR ORSAT — dónde el receptor escucha bien ahora',
    intro: 'Elija una banda: el mapa muestra, desde el receptor, las regiones desde donde las señales llegan bien (propagación medida por las ionosondas y diagrama real de la antena). Rueda del ratón sobre el mapa para hacer zoom.',
    labels: { G: 'buena recepción', M: 'recepción aceptable', P: 'recepción débil (antena poco favorable en este ángulo)',
              a: 'absorbida (capa D)', c: 'zona de silencio (MUF superada)', '-': 'sin datos' },
    nodata: 'sin datos (ninguna ionosonda lo bastante cerca)',
    hover: 'Pase el ratón por el mapa para ver el detalle de una zona.',
    cell: (band, az, r0, r1, label, muf) => `${band} · azimut ${az}° · ${r0}–${r1} km: ${label}${muf ? ` · MUF ${muf} MHz` : ''}`,
    receiver: (loc) => `Receptor: WebSDR ORSAT (${loc}). Antena: loop horizontal de 80 m de perímetro a 6 m del suelo, balun 4:1 (diagrama calculado con NEC).`,
    how: '¿Cada celda: pasa la banda desde allí (ionosondas medidas) y recibe bien la loop con ese ángulo de llegada?',
    note: (when) => `Proyección azimutal equidistante centrada en el WebSDR: distancias y azimuts reales desde el receptor. Rueda del ratón sobre el mapa: zoom. Cálculo de las ${when}. Mapa base y ciudades: Natural Earth (dominio público).`,
    aria: (band) => `Mapa de recepción de ORSAT en ${band}`,
    loading: 'Calculando el mapa…',
    west: 'O',
  },
};
