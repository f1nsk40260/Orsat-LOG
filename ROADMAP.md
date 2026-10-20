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
| Jour | Une page par jour **UTC** (tables `qso`, `session`, `propagation`, `weather`, `day_note`) |
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
- **Retour F1NSK 20/10 : ne fonctionne pas chez lui → à reprendre plus tard** (cause non diagnostiquée).

## Fait — v0.5.0 (20/10/2026) : QSO de groupe (tables rondes quotidiennes)
- Onglet **Groupe** dans la saisie : nom du QSO (ex. « QSO des Copains »), début / fin UTC, fréquence, mode.
- Nom déjà utilisé → créneau, fréquence et mode repris de la dernière session du même nom.
- Fenêtre de session : saisie rapide d'une station par ligne (Entrée), **habitués absents** proposés
  (présents dans les 10 dernières sessions du même nom) → ajout en un clic avec nom / QTH / locator.
- Heure du passage : maintenant si la session est en cours, sinon heure de début (saisie après coup).
- Clôturer (fin = maintenant), Modifier, Supprimer (avec ses QSO), Reprendre une session du jour.
- Chaque station = un QSO normal (`qso.session_id` → table `session`), marqué **GRP** dans les listes ;
  page du jour : pastilles des sessions (créneau, nombre de stations).
- ADIF : nom de la session en tête du COMMENT + champ `APP_ORSATLOG_SESSION`.
- v0.5.1 : **animateur** de la session (indicatif, repris de la dernière session du même nom) ;
  marqué ★, proposé en premier tant qu'il n'est pas contacté ; ADIF `APP_ORSATLOG_ANIMATOR`.
- v0.5.2 : la fenêtre de groupe **suit le TCI** (case « Suivre la radio ») à l'ouverture comme pour chaque
  station ajoutée (QSY en cours de ronde) ; **liste déroulante des noms préenregistrés** (table
  `group_template` : créneau, fréquence, mode, animateur habituels), « + Nouveau nom… », Préenregistrer
  sans ouvrir de session, ✕ pour retirer un nom (les QSO restent).

## Fait — mise à jour depuis l'interface (20/10/2026)
- Réglages → Mise à jour : version installée, liste des modifications disponibles sur GitHub,
  bouton « Mettre à jour et redémarrer » (lance `orsat-log.sh` détaché : pull, recompilation, relance).

## Fait — v0.6.0 (20/10/2026) : liaison avec la page du WebSDR ORSAT
- ORSAT-LOG ouvre un **serveur TCI local** sur `127.0.0.1:40001` (`backend/orsatlog/websdr.py`).
  La page ORSAT (bouton **CAT Sync**, `lib/catsync.js` de PhantomSDR-ORSAT, essaie 50001 et 40001)
  s'y connecte : le carnet reçoit la fréquence et le mode **réellement écoutés dans le navigateur**.
  Aucune modification du serveur ni de la page ORSAT.
- 50001 reste au transceiver (AetherSDR, ORSAT-LOG client) ; les deux liaisons coexistent.
- Panneau « WebSDR ORSAT » sous le transceiver ; en **SWL**, la saisie suit le WebSDR s'il est connecté,
  en QSO le transceiver (WebSDR à défaut).
- Clic sur une fréquence d'une entrée du carnet = la page WebSDR s'y recale (`POST /api/websdr/tune`).
- Limite : la page n'envoie sa fréquence qu'au premier réglage après connexion (touchez la fréquence une fois).
- Réglages → WebSDR ORSAT : activer / port (40001 par défaut).
- Écarté : le pont `tci-bridge/orsat-tci-server.py` de PhantomSDR-ORSAT ouvre sa propre écoute,
  indépendante du navigateur → gardé pour donner l'audio du WebSDR aux décodeurs, pas pour le carnet.

## Deux PC (question F1NSK 20/10)
- Code : aucun souci (GitHub). 2e PC = clé SSH sans phrase de passe + `git clone` + `./update.sh` une fois.
- **Données : base SQLite locale à chaque PC → carnets divergents.** Solutions proposées, choix en attente :
  dossier synchronisé (Syncthing/Nextcloud, jamais les deux PC ouverts en même temps) /
  sauvegarde-restauration complète dans les Réglages / un PC serveur accessible à distance.

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
- **WebSDR ORSAT** (page du navigateur, CAT Sync) : fait en v0.6.0, ORSAT-LOG = serveur TCI sur 40001.
- **Orsat-SDR** (plus tard) pour les logs SWL → nécessite d'ajouter un serveur TCI dans Orsat-SDR.

## Mode SWL — suite
- Fait en v0.3 : saisie de base (voir plus haut).
- À faire : identification automatique de la station par fréquence + heure via une grille de diffusion (EiBi)
  → émetteur et distance connus sans saisie : très utile pour l'analyse de propagation.
