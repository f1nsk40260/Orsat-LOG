# ORSAT-LOG

Carnet de trafic radioamateur orienté analyse de la propagation, installé sur le PC du
WebSDR **PhantomSDR-ORSAT** et servi par lui sous **https://orsat.ddns.net/log/**.

- **Exploitation** : depuis n'importe quel poste, dans un navigateur. Mot de passe = celui du
  panneau admin du WebSDR.
  - QSO / QSO de groupe : le navigateur se relie lui-même à AetherSDR (TCI, `ws://127.0.0.1:50001`
    sur le poste d'exploitation).
  - SWL : la page du WebSDR ouverte dans le même navigateur envoie fréquence et mode au carnet.
- **Gestion** : panneau admin du WebSDR, rubrique **Carnet ORSAT-LOG** : réglages (indicatif,
  locators station / WebSDR, TCI, météo), sauvegardes et restauration, mise à jour, état du service.

## Ce que fait le carnet

- **Agenda** : une page par jour UTC (saisie QSO / SWL / QSO de groupe, activité, notes, bilan),
  calendrier, pages passées en consultation. **Carnet complet** avec recherche, import et export ADIF,
  synchronisation automatique avec le logbook QRZ.com, envoi des QSO vers eQSL.cc et relève des eQSL reçues.
- **Fiche QSO** : conditions du contact (indices solaires, météo spatiale, ionosphère mesurée, trajet sur carte).
- **Propagation** : indices NOAA, météo spatiale (Kp, Bz, vent solaire, éruptions), bandes ouvertes et
  portée par bande d'après les ionosondes, carte des zones de silence, fenêtre **Trajet** (tracé de rayons,
  absorption D, chances de réception), **Analyse** du carnet (distances selon Kp, SFI, heure, direction).
- **Météo locale** (station Weathercloud) : courbes température / pression avec leurs échelles,
  bouton **Windy** pour ouvrir la carte Windy.
- **Orages et QRN** : foudre en temps réel (Blitzortung), orage le plus proche, rose des secteurs, écart du
  bruit par bande ; graphe 24 h avec échelles impacts (gauche) et bruit dB (droite), bouton **Blitz**
  pour ouvrir la carte Blitzortung.
- **Graphes zoomables** (Météo locale, Orages et QRN) : molette ou sélection à la souris sur l'axe du temps,
  ↺ pour revenir aux 24 h.
- **WebSDR** : stations entendues, mesure réelle du bruit et du SNR, indice de performance, page publique
  **/log/ecoute** (zone d'écoute par bande, FR / EN / ES).

## Installation sur le PC du WebSDR (une seule fois)

```bash
cd ~ && git clone https://github.com/f1nsk40260/Orsat-LOG.git
cd ~/Orsat-LOG && bash install-server.sh ~/PhantomSDR-Plus
```

Le script crée le service systemd `orsat-log` (priorité basse, plafonds CPU et mémoire), ajoute
`log_port` à `admin_config.json` et relance le proxy du WebSDR (quelques secondes de coupure).
Prérequis : Python 3 avec venv, Node.js/npm (nvm accepté).

## Mises à jour

Depuis le panneau admin (rubrique Carnet ORSAT-LOG → METTRE À JOUR), ou à la main :

```bash
bash ~/Orsat-LOG/update-server.sh && sudo systemctl restart orsat-log
```

## Données

Indices solaires historiques : archive Kp / ap / Ap / SN / F10.7 du GFZ Potsdam (Matzka et al., 2021,
*Space Weather*, https://doi.org/10.1029/2020SW002641), licence CC BY 4.0.

Ionosphère mesurée (fiche QSO) : ionosondes du réseau GIRO, Lowell GIRO Data Center (Reinisch, B. W., and
I. A. Galkin, *Global ionospheric radio observatory (GIRO)*, Earth Planets Space, 63, 377-381, 2011 ;
http://spase.info/SMWG/Observatory/GIRO), licence CC BY-NC-SA 4.0, usage non commercial ; l'observatoire
fournisseur est cité dans chaque fiche.

Identification des écoutes SWL : grille des émissions en ondes courtes EiBi (Eike Bierwirth),
http://www.eibispace.de/.

Indices solaires et météo spatiale en direct : NOAA Space Weather Prediction Center
(https://services.swpc.noaa.gov/). Bandes ouvertes et cartes de propagation : mesures d'ionosondes via
KC2G (https://prop.kc2g.com/, Andrew Rodland KC2G ; GIRO, NOAA, INGV, Australian SWS).

Foudre : flux public de la carte Blitzortung.org (https://www.blitzortung.org/), réseau communautaire de
détection, usage non commercial. Météo locale : Weathercloud (https://weathercloud.net/). Carte de vent :
lien vers Windy (https://www.windy.com/). Correspondants (nom, QTH, photo, logbook) : QRZ.com. Cartes QSL électroniques : eQSL.cc (https://www.eqsl.cc/).

Fonds de carte : © Esri, HERE, Garmin, Maxar, Earthstar Geographics ; © les contributeurs OpenStreetMap ;
Sentinel-2 cloudless by EOX IT Services GmbH (https://s2maps.eu, CC BY 4.0, données Copernicus Sentinel).

`~/Orsat-LOG/data/` (jamais envoyé sur GitHub) : base `orsatlog.db`, copies quotidiennes
`backups/`, clé de session `secret.key`.

## Développement

```bash
.venv/bin/python run.py                              # serveur sur 127.0.0.1:8740
cd frontend && npm run dev                           # interface avec rechargement à chaud
```

Voir [ROADMAP.md](ROADMAP.md) pour l'état du projet.
