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
| Base | SQLite : `~/Orsat-LOG/data/orsatlog.db`, journal `data/orsat-log.log` (dossier ignoré par git ; `ORSATLOG_DATA` pour changer). Jusqu'à v0.6.4 : `~/.local/share/orsat-log`, reprise automatique |
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
- Panneau « WebSDR ORSAT » sous le transceiver.
- **Règle F1NSK : le carnet suit selon le mode d'exploitation, sans repli.** SWL = page WebSDR ORSAT ;
  QSO et Groupe = transceiver (AetherSDR).
- Clic sur une fréquence du carnet (`POST /api/tune`) : entrée SWL = la page WebSDR se recale ;
  QSO / groupe = le transceiver se règle (et la page le suit par CAT Sync).
- v0.6.1 : la page suit AetherSDR sans le relayer au carnet → le carnet recopie les changements de
  fréquence/mode d'AetherSDR dans le panneau WebSDR (si la page a déjà parlé). Pas de réponse à la
  question PTT de la page (un « trx:0,false » pourrait rétablir son son pendant une émission).
- Limite : la page n'envoie sa fréquence qu'au premier réglage après connexion (touchez la fréquence une fois).
- Réglages → WebSDR ORSAT : activer / port (40001 par défaut).
- v0.6.2 : écoute sur 127.0.0.1 **et ::1** — la page cherche « localhost », résolu d'abord en IPv6
  sous Linux ; en IPv4 seule, la page ne trouvait pas le carnet (retour F1NSK).
- v0.6.3 : listes déroulantes au style ORSAT (WebKitGTK les dessinait en thème clair : mode illisible,
  blanc sur blanc) ; rendu DMA-BUF de WebKitGTK désactivé (plantage WebKitWebProcess) ; le lanceur
  recompile l'interface si ses sources sont plus récentes que `dist`.
- v0.6.4 : bouton **Tout recompiler** dans Réglages → Mise à jour (= `orsat-log --rebuild`).
- v0.6.5 : base et journal dans `~/Orsat-LOG/data/` (demande F1NSK) ; ancienne base reprise au premier
  lancement et gardée en `~/.local/share/orsat-log/orsatlog.db.ancien`.
- Écarté : le pont `tci-bridge/orsat-tci-server.py` de PhantomSDR-ORSAT ouvre sa propre écoute,
  indépendante du navigateur → gardé pour donner l'audio du WebSDR aux décodeurs, pas pour le carnet.

## Fait — v0.7.0 (20/10/2026) : édition complète d'une entrée
- Bouton ✎ sur chaque ligne (page du jour et carnet complet), ou double-clic sur la ligne.
- Fenêtre d'édition : type QSO/SWL, indicatif / station, date et heure UTC, fréquence, mode + sous-mode
  (USB/LSB en SSB), reports (RST ou SINPO), locator, nom, QTH / émetteur, commentaire / programme,
  contexte propagation (SFI, A, K). Supprimer depuis la fenêtre. Entrée = enregistrer, Échap = annuler.
- Passage de QSO de groupe : rattachement conservé, ou détaché (case à décocher ; un SWL est toujours détaché).
- Serveur (`PUT /api/qsos/{id}`) : contrôle date / heure / locator / indicatif ; bande, distance et azimut
  recalculés.
- v0.7.1 : pastilles des QSO de groupe de la page du jour : ✎ = ouvrir la session dans l'onglet Groupe
  (Modifier / Clôturer / Supprimer), ✕ = supprimer la session et ses QSO.

## Fait — v0.8.0 (20/10/2026) : mode d'exploitation impossible à rater
- Trois grands onglets (icône + libellé + sous-titre) : **QSO** vieil or, **SWL** bleu, **Groupe** vert ;
  cadre, titre et bouton d'enregistrement du formulaire à la couleur du mode.
- Bouton explicite : « Enregistrer le QSO », « Enregistrer l'écoute », « Ajouter au groupe ».
- Bandeau de suggestion (jamais de bascule automatique) : émetteur éteint + WebSDR relié en QSO/Groupe
  → « Passer en SWL » ; PTT d'AetherSDR ou WebSDR absent en SWL → « Passer en QSO » ; ✕ pour ignorer.
- **Préférence F1NSK : pas de raccourcis clavier, tout à la souris (molette quand utile).**

## Décidé (20/10/2026) : ORSAT-LOG serveur central sur le PC ORSAT
Motifs : une seule base (Main-PC à distance par fibre, saint paul sur le réseau d'ORSAT, usage nomade),
relevés propagation/météo en continu, mutualisation avec PhantomSDR-ORSAT.
- **Adresse** : `https://orsat.ddns.net/log`. ORSAT-LOG en interne (`127.0.0.1:8740`), exposé par
  `proxy.py` de PhantomSDR-ORSAT (règle `/log*`, distincte de `/logs/…`), comme `/admin`.
- **Accès** : compte unique, **mot de passe commun avec le panneau admin ORSAT** : le carnet lit
  `admin_config.json` (lecture seule) et vérifie avec la même méthode PBKDF2 que `admin_server.py`.
  Protection anti-rafale de `proxy.py` étendue à la connexion de `/log`.
- **Seul fichier d'ORSAT 1.0 modifié** : `proxy.py` (routage + protection) → redémarrage du proxy,
  coupure de quelques secondes du WebSDR. Le reste est à côté : service systemd dédié, plafonds
  mémoire/CPU, dossier et base propres.
- **Postes d'exploitation = un navigateur** : SWL → la page WebSDR (même adresse) envoie sa fréquence
  au carnet central (retouche de la page ORSAT, future 1.1) ; QSO → l'interface du carnet ouverte dans
  le navigateur du PC d'AetherSDR se connecte elle-même à `ws://localhost:50001`. Fin de pywebview.
- **Sauvegardes** : copie quotidienne automatique sur le serveur + bouton « Télécharger une sauvegarde ».
- **Ordre** : 1) socle (carnet central, connexion, accès navigateur, sauvegardes) ; 2) liaison directe
  page WebSDR ↔ carnet ; 3) mutualisations une par une (propagation/météo collectées une seule fois,
  DX cluster croisé avec le carnet, historique d'une station dans la page WebSDR, décodages FT8/WSPR
  des navigateurs → écoutes SWL automatiques ; **pas de décodage côté serveur** : charge CPU).
- Charge estimée (ordre de grandeur, non mesuré) : 60–100 Mo RAM, CPU quasi nul.

## Fait — v0.9.0 (20/10/2026) : socle serveur central, étape 1 (connexion + navigateur)
- `run.py --central [--host 0.0.0.0] [--port 8740]` : serveur sans fenêtre, accès par mot de passe.
- Mot de passe : `admin_config.json` du WebSDR (lecture seule, PBKDF2 ou ancien SHA-256),
  chemin `ORSATLOG_PASSWORD_FILE` ou `~/PhantomSDR-Plus/admin_config.json` ; à défaut mot de passe
  propre au carnet `data/auth.json` (`run.py --set-password`, pour l'essai sur saint paul).
- Page de connexion au style ORSAT ; session = cookie signé 30 jours (`data/secret.key`), Secure en https ;
  bouton **Déconnexion** ; anti-rafale 5 échecs / 10 min → 10 min de blocage (adresse réelle prise dans
  X-Forwarded-For seulement si la requête vient de la boucle locale, c.-à-d. de proxy.py).
- Interface en chemins relatifs (`base: './'`, `api/…`, `ws`) : marche à la racine comme derrière `/log/`
  (le proxy devra rediriger `/log` → `/log/`).
- En central, le serveur n'ouvre ni TCI AetherSDR ni port WebSDR : **le navigateur se connecte lui-même**
  à AetherSDR (`frontend/src/tciBrowser.js`, réglages TCI = adresse vue depuis le PC de l'opérateur) ;
  clic sur une fréquence d'un QSO = réglage par cette liaison.
- Limite en central jusqu'à l'étape 2 : pas de suivi de la page WebSDR en SWL (saisie manuelle).
- Mise à jour depuis les Réglages désactivée en central (se fera par le service, étape 3).
- Mode bureau inchangé.

## Fait — v0.9.1 (20/10/2026) : installation sur le PC ORSAT (étape 3 avancée)
- `install-server.sh [dossier WebSDR]` (défaut `~/PhantomSDR-Plus`) : venv serveur (sans pywebview),
  compilation de l'interface en `nice`, service systemd `orsat-log` (Nice=10, CPUQuota=30 %,
  MemoryMax=300M, Restart=always, `ORSATLOG_PASSWORD_FILE` = admin_config.json du WebSDR),
  ajout de `log_port: 8740` à admin_config.json (copie `.avant-orsat-log`), redémarrage de
  `phantomsdr-proxy`, vérification.
- PhantomSDR-ORSAT `proxy.py` : `/log` = service annexe (comme /rade, /stats, /relay), préfixe retiré,
  `/log` → `/log/` ; inactif sans `log_port`. Chaîne proxy → carnet testée (connexion, assets, API, WebSocket).
- Dépendance ajoutée : `python-multipart` (formulaire de connexion).
- **En service le 20/10/2026 sur le PC ORSAT : https://orsat.ddns.net/log/** (retour F1NSK : aucune charge
  notable). Mise à jour serveur : `cd ~/Orsat-LOG && git pull && bash install-server.sh ~/PhantomSDR-Plus`.
- Reprise de la base de Main-PC : **abandonnée** (F1NSK : le serveur repart d'une base neuve).

## Fait — v0.10.0 (20/10/2026) : sauvegardes
- Copie automatique quotidienne `data/backups/orsatlog-AAAAMMJJ.db` (au démarrage si absente, contrôle
  toutes les heures), API de sauvegarde SQLite (cohérente en cours d'utilisation), 30 copies gardées.
- Réglages → Sauvegardes : 5 dernières copies téléchargeables, « Télécharger une sauvegarde » (copie fraîche),
  « Restaurer… » (fichier .db vérifié : intégrité + table qso ; base actuelle sauvegardée d'abord en
  `orsatlog-AAAAMMJJ-HHMM.db` ; migrations rejouées).
- `install-server.sh` ne relance plus le proxy du WebSDR lors d'une simple mise à jour (`FORCE_PROXY=1` pour forcer).

## Fait — v0.11.0 (21/10/2026) : liaison directe page WebSDR ↔ carnet central (étape 2)
- Carnet central : WebSocket `/tci` (session requise) qui parle TCI comme le port 40001 du mode bureau ;
  la page WebSDR s'y connecte par `wss://orsat.ddns.net/log/tci`. Panneau WebSDR actif en central.
- PhantomSDR-ORSAT (page) : `catsync.js` accepte une adresse complète (`config.url`) ; au chargement,
  la page sonde `/log/api/info` — si ce navigateur a une session au carnet, le carnet est ajouté aux
  sources TCI (50001, 40001, « carnet ORSAT-LOG »). Auditeurs sans session : une requête 401, rien d'autre.
- Clic sur une écoute SWL = la page se recale ; QSO = AetherSDR par la liaison du navigateur.
- Miroir : l'interface du carnet signale au serveur les changements d'AetherSDR (`/api/websdr/mirror`),
  que la page suit sans les relayer.
- Condition : ouvrir la page WebSDR en **https** (cookie de session « Secure »), dans un navigateur
  connecté au carnet.
- v0.11.1 (retour F1NSK : pas de synchro) : la page n'envoyait rien sans CAT Sync, réglage mémorisé par
  adresse (http:8080 ≠ https). Désormais **liaison propre au carnet, indépendante de CAT Sync** : la page
  envoie fréquence + mode dès la connexion puis à chaque changement (y compris ceux venus d'AetherSDR),
  et obéit aux recalages du carnet. Le carnet ne répond plus aux questions `vfo:0;` / `modulation:0;`.

## Architecture d'exploitation (F1NSK, 21/10/2026)
- Serveur unique (PC ORSAT) : PhantomSDR-ORSAT + ORSAT-LOG, `https://orsat.ddns.net` (+ `/log/`).
- Trois postes clients (QTH A, QTH B, nomade) : AetherSDR et/ou page ORSAT dans un navigateur ;
  **un seul poste à la fois**, jamais deux simultanément. Les postes ne sont que des télécommandes.
- Station émettrice fixe : FlexRadio (sous AetherSDR) en **IN93KU**. Récepteur WebSDR ORSAT en **IN93LR**.

## Fait — v0.12.0 (21/10/2026) : deux locators
- Réglages → Station : « Locator station (QSO) » et « Locator WebSDR (SWL) » (vide = celui de la station).
- Distances / azimuts : QSO depuis la station, SWL depuis le WebSDR ; ADIF `MY_GRIDSQUARE` idem.
- Changement de locator → recalcul de tout le carnet (`POST /api/recompute`).

## Fait — v1.0.0 (21/10/2026) : un seul centre de gestion, fin de la version bureau
- **Réglages déplacés dans le panneau admin du WebSDR**, rubrique « Carnet ORSAT-LOG »
  (`admin_extras.py` / `admin_extras.js` de PhantomSDR-ORSAT) : état du service (version, QSO/SWL,
  taille de la base, pages reliées), station (indicatif, 2 locators, météo), TCI, sauvegardes
  (téléchargement, restauration), mise à jour (`update-server.sh` puis redémarrage par systemd).
- Le panneau parle au carnet en interne (127.0.0.1:log_port) avec l'en-tête `X-OrsatLog-Admin` =
  HMAC-SHA256(password_hash, "orsatlog-admin") ; réglages en écriture, sauvegardes et restauration
  **réservés au panneau** (403 sinon). Le carnet lit seulement les réglages (pour le TCI du navigateur).
- Carnet : plus de bouton Réglages ; si l'indicatif manque, l'en-tête l'indique (« À régler : panneau admin »).
- **Version bureau supprimée** : `orsat-log.sh`, `update.sh`, `tci.py` (TCI côté serveur), port local
  40001, fenêtre pywebview, `--central`, `--set-password`, reprise de `~/.local/share/orsat-log`,
  mise à jour depuis l'interface. `run.py` = serveur seul. Mot de passe = panneau admin uniquement.
- Le service `orsat-log` apparaît aussi dans « Santé du serveur » du panneau.

## Fait — v1.1.0 (21/10/2026) : carnet de trafic et journal d'écoute séparés
- Motif (F1NSK) : les écoutes SWL ne doivent jamais partir vers QRZ.com avec les contacts.
- Une seule table (`qso.kind` = QSO / SWL), mais deux carnets partout ailleurs :
  - **Carnet de trafic** = QSO + QSO de groupe ; `db.traffic_qsos()` (garde-fou : ne renvoie que
    `kind = 'QSO'`) ; export `api/export/adif` → `orsat-log_trafic_AAAAMMJJ.adi`. **Seule source
    autorisée pour la future synchro QRZ.com / LoTW / eQSL.**
  - **Journal d'écoute** = SWL ; `db.listening_qsos()` ; export à part `api/export/adif-swl`
    → `orsat-log_ecoutes_AAAAMMJJ.adi` (SWL:Y).
  - `adif.export(kind=…)` écarte toujours les entrées de l'autre type.
- Interface : bouton ADIF du header supprimé ; « Carnet » = deux onglets (⇄ Carnet de trafic, ◉ Journal
  d'écoute) avec chacun son export. La page du jour garde les deux côte à côte (analyse de propagation).

## Deux PC (question F1NSK 20/10) — sans objet depuis le serveur central
- Code : aucun souci (GitHub). 2e PC = clé SSH sans phrase de passe + `git clone` + `./update.sh` une fois.
- **Données : base SQLite locale à chaque PC → carnets divergents.** Solutions proposées, choix en attente :
  dossier synchronisé (Syncthing/Nextcloud, jamais les deux PC ouverts en même temps) /
  sauvegarde-restauration complète dans les Réglages / un PC serveur accessible à distance.

## À faire (ordre proposé)
1. Import ADIF (reprise de l'ancien carnet).
2. ~~Édition d'un QSO existant~~ (fait en v0.7.0).
3. Onglet **Analyse** : QSO par bande × heure UTC, carte des contacts (grand cercle depuis le QTH),
   distances max par bande, corrélation avec SFI/K.
4. Recherche / filtres dans le carnet (indicatif, bande, mode, période).
5. Préfixes → pays DXCC (cty.dat) et entité dans chaque QSO.
6. Spots TCI / DX cluster, croisement RBN / PSKReporter.
7. Envoi de commandes TCI (cliquer un spot = changer de fréquence).
8. Upload LoTW / QRZ / eQSL — **uniquement depuis `db.traffic_qsos()`** (jamais les SWL).

## Sources TCI visées
- **AetherSDR** (serveur TCI v2.0 : CAT, audio, IQ, CW, spots, événements récepteur ; FlexRadio en priorité,
  aussi récepteurs en réception seule). Port 50001 (applet « TCI Server » d’AetherSDR, à démarrer).
- **WebSDR ORSAT** (page du navigateur, CAT Sync) : fait en v0.6.0, ORSAT-LOG = serveur TCI sur 40001.
- **Orsat-SDR** (plus tard) pour les logs SWL → nécessite d'ajouter un serveur TCI dans Orsat-SDR.

## Mode SWL — suite
- Fait en v0.3 : saisie de base (voir plus haut).
- À faire : identification automatique de la station par fréquence + heure via une grille de diffusion (EiBi)
  → émetteur et distance connus sans saisie : très utile pour l'analyse de propagation.
