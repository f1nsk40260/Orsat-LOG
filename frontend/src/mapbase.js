// Fonds de carte communs (fiche QSO, fenêtre « Entendu ») : sans clé d'API, au choix à la souris
// en haut à droite, choix retenu par le navigateur. Filtres d'assombrissement dans theme.css.
export function addFonds(L, map) {
  const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
  const fonds = {
    'Nuit': L.tileLayer(ESRI + 'Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 8, noWrap: true, className: 'fond-nuit', attribution: 'Fond © Esri, HERE, Garmin, © OpenStreetMap' }),
    'Satellite': L.tileLayer(ESRI + 'World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 8, noWrap: true, className: 'fond-sat', attribution: 'Imagerie © Esri, Maxar, Earthstar Geographics' }),
    'Plan OSM sombre': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 8, noWrap: true, className: 'osm-dark', attribution: '© OpenStreetMap' }),
  };
  let choix = 'Nuit';
  try { if (fonds[localStorage.getItem('orsatlog.fond')]) choix = localStorage.getItem('orsatlog.fond'); } catch {}
  fonds[choix].addTo(map);
  L.control.layers(fonds, null, { position: 'topright' }).addTo(map);
  map.on('baselayerchange', (e) => { try { localStorage.setItem('orsatlog.fond', e.name); } catch {} });
}
