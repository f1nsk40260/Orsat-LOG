# ORSAT-LOG — Feuille de route

Carnet de trafic radioamateur, simple à utiliser, connecté en **TCI**, orienté **analyse de la propagation**.
Style ORSAT (thème vieil or `rgb(207,181,59)`), Linux en priorité.

## Méthode de travail
- Claude écrit et pousse le code dans ce dépôt (`f1nsk40260/Orsat-LOG`, privé).
- Sur Main-PC : `~/Orsat-LOG`. Usage courant : icône ORSAT-LOG (Bureau/menu) ou commande `orsat-log`
  = récupère les modifs, recompile ce qui a changé, relance. `./update.sh` = installation complète.
- Retours de test : messages du terminal ou capture d'écran → correction → nouveau push.
- Petites livraisons : une fonction = un commit qui tourne.
- **Ce fichier est la mémoire du projet** : à mettre à jour à chaque livraison.

## Décisions techniques
| Sujet | Choix |
|---|---|
| Interface | Svelte 5 + Vite (`frontend/`), compilée dans `frontend/dist` |
| Backend | Python 3, FastAPI + uvicorn (`backend/orsatlog/`) |
| Fenêtre | pywebview (GTK/WebKit), repli automatique sur le navigateur |
| Base | SQLite : `~/.local/share/orsat-log/orsatlog.db` (variable `ORSATLOG_DATA` pour changer) |
| Radio | TCI WebSocket, port 50001 par défaut (AetherSDR ; ExpertSDR = 40001), récepteur choisi / VFO A |
| Solaire | hamqsl.com (SFI, A, K, X-ray), cache 15 min, figé dans chaque QSO |
| Météo | Weathercloud (station perso), relevé 15 min, table `weather` |
| Échange | ADIF 3.1 (export fait, SWL = `SWL:Y`, import à faire) |
| Jour | Une page par jour **UTC** (tables `qso`, `propagation`, `day_note`) |
| Port local | 8740 |

## Fait — v0.1.0 (20/10/2026)
- Squelette backend + frontend, thème ORSAT.
- Connexion TCI : fréquence, modulation, PTT, nom de l'appareil, reconnexion auto.
- Saisie QSO : heure UTC figée à la frappe de l'indicatif, fréquence/mode suivis depuis la radio,
  RST par défaut selon le mode, « déjà contacté » à la sortie du champ indicatif.
- Distance et azimut calculés depuis les locators.
- Contexte solaire (SFI/A/K) enregistré avec chaque QSO.
- Liste des QSO, suppression, export ADIF.
- Réglages : indicatif, locator, hôte/port TCI.
- Repli silencieux sur le navigateur si WebKit GTK absent (Main-PC : `sudo apt install gir1.2-webkit2-4.1`).

## Fait — v0.2.0 (20/10/2026)
- Compatibilité AetherSDR (vérifiée sur son code source) : port 50001, modes fm/cwr/rtty.
- Réglage du récepteur TCI suivi (slice A/B/C/D).
- Cause d'échec de connexion TCI affichée dans l'interface.
- Lanceur `orsat-log` (icône Bureau/menu) : mise à jour + recompilation incrémentale + relance.

## Fait — v0.3.0 (20/10/2026) : fonctionnement en AGENDA
- Principe : **une page par jour UTC** (bascule à 00:00 UTC). Ouverture sur la page du jour.
- Page du jour : transceiver, saisie, activité du jour (QSO + SWL), propagation du jour,
  notes libres (enregistrement auto), bilan (bandes, plus longue distance), emplacement Météo.
- Pages passées : consultation (archives), notes modifiables, pas de saisie.
- Navigation : ◀ ▶, calendrier du mois (points QSO / SWL / note), Alt+← Alt+→ Alt+↓.
- **Carnet complet** uniquement via le bouton « Carnet » du header (Alt+C), avec recherche et filtre QSO/SWL ;
  clic sur une date = ouverture de la page de ce jour.
- Relevé automatique de la propagation (hamqsl) toutes les 15 min → table `propagation`
  (≥ 1 point/heure + à chaque nouvelle publication) ; frise K + SFI sur 24 h, état des bandes jour/nuit.
- **Mode SWL** (base) : bascule QSO/SWL dans la saisie ; station entendue (casse libre), SINPO,
  locator et site de l'émetteur ; bandes de radiodiffusion (« 31m BC ») ; export ADIF `SWL:Y`.
- Contexte solaire de secours : dernier relevé enregistré si hamqsl ne répond pas.

## Fait — v0.4.0 (20/10/2026) : météo locale
- Station Weathercloud de F1NSK à Castets (identifiant 9224966553, modifiable dans Réglages → Météo,
  adresse complète acceptée).
- Adresse non officielle `app.weathercloud.net/device/values?code=…` (en-tête `X-Requested-With`
  + cookie de session récupéré automatiquement). Peut changer sans préavis : à surveiller.
- Relevé toutes les 15 min (table `weather`, une ligne par nouvelle mesure), au plus 1 requête / 5 min.
- Panneau Météo de la page du jour : température, humidité, rosée, pression + tendance 3 h,
  vent (direction, rafales), pluie, soleil/UV, mini/maxi, courbes température + pression 24 h.
- Constat 20/10 : la page Weathercloud de la station affichait « - » partout (station n'émettant plus ?).

## À faire (ordre proposé)
1. Import ADIF (reprise de l'ancien carnet).
2. Édition d'un QSO existant.
3. Onglet **Analyse** : QSO par bande × heure UTC, carte des contacts (grand cercle depuis le QTH),
   distances max par bande, corrélation avec SFI/K.
4. Recherche / filtres dans le carnet (indicatif, bande, mode, période).
5. Préfixes → pays DXCC (cty.dat) et entité dans chaque QSO.
6. Spots TCI / DX cluster, croisement RBN / PSKReporter.
7. Envoi de commandes TCI (cliquer un spot = changer de fréquence).
8. Upload LoTW / QRZ / eQSL.

## Sources TCI visées
- **AetherSDR** (serveur TCI v2.0 : CAT, audio, IQ, CW, spots, événements récepteur ; FlexRadio en priorité,
  aussi récepteurs en réception seule). Port 50001 (applet « TCI Server » d’AetherSDR, à démarrer).
- **Orsat-SDR** (plus tard) pour les logs SWL → nécessite d'ajouter un serveur TCI dans Orsat-SDR.

## Mode SWL — suite
- Fait en v0.3 : saisie de base (voir plus haut).
- À faire : identification automatique de la station par fréquence + heure via une grille de diffusion (EiBi)
  → émetteur et distance connus sans saisie : très utile pour l'analyse de propagation.
