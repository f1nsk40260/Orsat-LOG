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
- **Vérifié 21/10 : la météo fonctionne** (63 relevés enregistrés ce jour-là sur la page du jour). Ne plus la dire en panne.
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

## Fait — v1.2.0 (21/10/2026) : import ADIF (carnet de trafic uniquement)
- Carnet → onglet « Carnet de trafic » → **Importer (ADIF)** : aperçu (lus, à ajouter, période, doublons,
  écoutes écartées, illisibles + motifs, exemples), puis « Importer N contacts ».
- `POST api/import/adif` (`confirm=false` = aperçu sans écriture) ; sauvegarde de la base avant l'import ;
  une seule transaction (`db.import_traffic`, n'insère que `kind = 'QSO'`).
- `adif.parse` : longueurs en octets (comme notre export), balises insensibles à la casse, en-tête ignoré.
  `adif.to_entry` : **SWL:Y écartées**, indicatif + date + heure obligatoires, TIME_ON HHMM accepté,
  FREQ en MHz → Hz, COMMENT ou NOTES.
- Doublon = même indicatif, date, heure à la minute et bande (aussi entre lignes du fichier).
- Bande recalculée depuis FREQ (sinon BAND du fichier) ; distance / azimut depuis le locator station ;
  SFI/A/K laissés vides (inconnus pour un contact ancien).
- Pas d'import dans le journal d'écoute (décision F1NSK).
- v1.2.1 (retour F1NSK : export QRZ.com refusé) : longueurs ADIF en **caractères** (QRZ.com compte ainsi ;
  le comptage en octets tronquait les valeurs accentuées), lecture UTF-8 sinon Latin-1, export aligné.
  Le refus venait surtout du proxy du WebSDR (limite aiohttp 1 Mo) : PhantomSDR-ORSAT `proxy.py` accepte
  désormais 60 Mo sous `/log` seulement. Testé avec l'export QRZ réel de F1NSK (4,6 Mo, 4 603 QSO :
  4 596 importés, 7 doublons QRZ, < 1 s).

## Fait — v1.3.0 (21/10/2026) : synchronisation automatique avec le logbook QRZ.com
- Décision F1NSK : remplace l'import ADIF. **v1.3.1 : synchro validée par F1NSK (base peuplée depuis QRZ),
  import ADIF retiré** (route, `db.import_traffic`, bouton et aperçu). `adif.parse` / `to_entry` servent à la synchro.
- `backend/orsatlog/qrz.py` (QRZ Logbook API, https://logbook.qrz.com/api ; abonnement QRZ requis) :
  - 1er passage : tout le logbook QRZ (FETCH par pages de 250, AFTERLOGID) ; ensuite MODSINCE toutes les
    15 min (`PERIOD`) ; les contacts du carnet absents de QRZ partent (INSERT).
  - Saisie / correction d'un QSO dans le carnet → `qrz_state = 'pending'` → envoi ~5 s après.
    Correction d'un QSO déjà chez QRZ : relecture QRZ (LOGIDS) puis INSERT OPTION=REPLACE ; si QRZ crée
    un nouveau numéro (indicatif / date / heure changés), l'ancien est supprimé.
  - Champs QRZ non gérés par le carnet (QSL, LoTW, pays, zones…) gardés dans `qso.adif_extra` et renvoyés
    tels quels : une correction ne fait rien perdre chez QRZ.
  - Correspondance carnet ↔ QRZ : `qso.qrz_logid`, sinon indicatif + date + HHMM + bande (bande vide = compatible).
  - **SWL jamais envoyées** (`db.qrz_pending` : kind = 'QSO'). Un QSO passé en SWL reste chez QRZ (noté au journal).
  - **Suppressions jamais automatiques** : le carnet demande à chaque suppression d'un QSO synchronisé
    « aussi chez QRZ ? » (définitif). Gardé chez QRZ → table `qrz_ignored`, la synchro ne le reprend plus
    (idem pour les QSO d'une session de groupe supprimée).
  - User-Agent `ORSAT-LOG/<version> (F1NSK)` ; réponse découpée sur les clés connues (l'ADIF contient des &).
- Panneau admin → Carnet ORSAT-LOG → carte **Synchronisation QRZ.com** : clé (vérifiée par STATUS avant
  enregistrement, jamais renvoyée ; `qrz_api_key` retirée de `/api/settings` hors panneau), synchro auto,
  « Synchroniser maintenant », « Relire tout QRZ », compteurs (synchronisés / en attente / refusés), journal.
- Carnet : repère sur chaque QSO (✓ synchronisé, ⏳ en attente, ⚠ refusé + motif).
- Testé contre un faux QRZ (API documentée) chargé de 600 QSO du vrai logbook QRZ de F1NSK.

## Fait — v1.4.0 (21/10/2026) : enrichissement des QSO (préalable à l'Analyse)
- Constat sur le logbook QRZ de F1NSK (4 603 QSO, 2008-2026) : **4 144 QSO faits depuis IN93LR**, 393 depuis
  IN93KU (+ IN93, IN93KV) → chaque QSO garde son QTH d'émission (`qso.my_gridsquare`, MY_GRIDSQUARE QRZ ;
  saisie du jour = locator station). Distances / azimuts calculés depuis ce QTH ; un changement de locator
  station ne touche plus les anciens QSO. Écoutes SWL : toujours depuis le locator WebSDR.
- Données QRZ promues en colonnes (`enrich.promote`) : country, dxcc, cont, cqz, ituz, lat/lon (ADIF
  « N031 13.700 »), confirmed (LoTW / QSL / eQSL). Correspondant sans locator : distance depuis ses
  coordonnées (`geo.adif_coord`, `distance_bearing` accepte (lat, lon)).
- SFI / A / K historiques (`enrich.py`) : archive GFZ Potsdam `Kp_ap_Ap_SN_F107_since_1932.txt`
  (kp.gfz.de, repli kp.gfz-potsdam.de ; CC BY 4.0, Matzka et al. 2021), relue chaque semaine dans
  `data/gfz_kp_ap_f107.txt`. SFI = F10.7 observé du jour, A = Ap du jour, K = Kp du créneau de 3 h du QSO ;
  `qso.solar_src` = 'GFZ' (archive) ou 'hamqsl' (relevé à la saisie). Seuls les QSO sans SFI ni K sont complétés.
- Passe d'enrichissement au démarrage (+30 s), chaque jour, et après chaque synchro QRZ ; idempotente.
- Carnet : colonne **Pays** (survol : DXCC, continent, zones CQ / ITU ; ◆ = confirmé), distance (survol :
  « depuis IN93LR »), SFI / K grisés quand ils viennent de l'archive.
- Panneau admin (état du carnet) : entités DXCC, confirmés, SFI/K connus (dont GFZ), distance connue.

## Fait — v1.5.0 (21/10/2026) : fiche QSO (« les conditions dans lesquelles il a été fait »)
- Clic sur l'indicatif (page du jour, carnet) → fiche ; « ✎ Modifier » y renvoie à l'édition.
- Carte Leaflet (fond CARTO dark) : trajet orthodromique depuis le QTH d'émission du QSO (`sun.js`
  greatCircle, coupé à l'antiméridien) ; **jour / nuit et ligne grise à l'instant UTC du QSO**, calculés
  pixel par pixel (`shadeImage` : hauteur du Soleil, NOAA ; or = Soleil entre +6° et −6°, sombre la nuit).
  Hauteur du Soleil et « jour / ligne grise / crépuscule / nuit » chez soi et chez le correspondant.
- `GET api/qsos/{id}/context` : SFI, Ap, taches (SN) du jour et **8 créneaux Kp** (archive GFZ, créneau du
  QSO encadré), SFI des 7 jours autour (+ tendance), position dans le cycle solaire (`enrich.CYCLES` :
  23 1996-08/2001-11, 24 2008-12/2014-04, 25 2019-12/2024-10 provisoire), relevé hamqsl du carnet le plus
  proche, autres QSO du même jour sur la bande, historique avec la station.
- Vérifié dans Chromium (captures) sur 4Z7AHG (nuit / nuit) et ES4MM (jour chez soi, ligne grise chez lui).

## Fait — v1.6.0 (21/10/2026) : ionosphère mesurée dans la fiche QSO (ionosondes GIRO)
- `ionosonde.py` : DIDBase GIRO, `https://lgdc.uml.edu/fastchar/getbest` (foF2, MUF(D) D=3000 km, foEs ;
  texte, en-tête « # », « --- » = absent ; vérifié depuis le serveur ORSAT : Roquetes depuis 1988, Dourbes
  depuis 2001). Liste des stations relue chaque semaine (DIDBFastStationList → `data/giro_stations.json`),
  secours : 23 stations européennes. Requêtes espacées de 1,2 s (sinon 429). `/common/DIDBGetValues` = 404.
- Point de réflexion : milieu du trajet si ≤ 4000 km, sinon 1er et dernier saut (sauts ≤ 4000 km).
  Ionosonde la plus proche ≤ 1500 km ayant une mesure à ±45 min ; sinon les 2 suivantes ; sinon on le dit.
- MUF du saut = MUF(3000) mesurée ramenée à la longueur réelle du saut (sécante, Terre sphérique, h 300 km).
  Verdict : fréquence ≤ 85 % MUF « franche », ≤ 100 % « en limite », au-delà « pas par F2 seule ».
- `GET api/qsos/{id}/iono[?refresh=true]` : chargé après la fiche, mémorisé (table `iono_cache`, clé
  date+heure+trajet+fréquence ; pas de mise en cache si GIRO injoignable). Carte : point(s) de réflexion
  et ionosonde(s). Courbe ±2 h foF2 / MUF(3000) / foEs + fréquence du QSO. Note Es si foEs ≥ 5 MHz.
- Licence CC BY-NC-SA 4.0 : crédit GIRO (Reinisch & Galkin 2011) et observatoire affichés dans la fiche.
- Testé hors ligne (GIRO injoignable depuis le bac à sable) : à valider sur le serveur.

## Fait — v1.6.1 / v1.6.2 (21/10/2026) : fond de carte sans clé, au choix (Nuit, Satellite, Plan OSM sombre)
- CARTO répondait « API key required » : fond Esri World Dark Gray (sans clé), repli OSM assombri.

## Fait — v1.6.3 (21/10/2026) : nouveaux QSO
- Archive GFZ relue chaque jour (au lieu de chaque semaine) : Kp de la veille disponible pour les QSO récents.
- Ionosphère d'un QSO de moins de 6 h : non mémorisée (« provisoire »), réinterrogée à chaque ouverture.

## Fait — v1.7.0 (21/10/2026) : identification des écoutes SWL par la grille EiBi
- `eibi.py` : grille `sked-a26.csv` / `sked-b26.csv` (saison A = dernier dim. de mars → dernier dim.
  d'octobre) et `README.TXT` (partie IV, sites d'émission avec coordonnées) de www.eibispace.de, gardés
  dans `data/eibi/`, relus chaque semaine ; saison absente (B26 en 404 le 21/10) → saison précédente.
  Filtres : fréquence ±1,5 kHz, heure, jours (vide, « 1245 », « Mo-Fr », « 24Oct »), validité jjmm.
  Site : « t » = site du pays de la station, « /D-r » = site r en Allemagne, vide = site unique du pays.
  Classement : écart de fréquence, horaire certain, site connu, cible Europe / mondiale.
- `GET api/eibi?freq=Hz[&date=AAAAMMJJ&time=HHMM]`. Formulaire SWL : suggestions sous la saisie, un clic
  remplit station (si vide), site, locator, commentaire (langue → cible). Fiche d'une écoute : rubrique
  « Qui émettait ? » ; un clic enregistre site + locator et recalcule trajet et ionosphère.
- Formats relevés sur le serveur ORSAT ; testé sur des extraits (eibispace.de injoignable d'ici).

## Fait — v1.7.1 / v1.7.2 (21/10/2026) : header au style ORSAT (bandeau semi-opaque en 1.7.2)
- Indices SFI/A/K retirés du header (déjà dans le panneau propagation).
- Horloge du WebSDR (`HeaderClock.svelte`, TU / LOCAL, clé `phantom.clockUtc` partagée avec la page).
- Fond d'écran ORSAT (`assets/background.jpg`, copie de celui de PhantomSDR-ORSAT).

## Fait — v1.7.3 (21/10/2026) : infobulles des valeurs de propagation
- `proptips.js` : ce que mesure l'indice + lecture de la valeur affichée (SFI, A, K/Kp, taches, X-ray,
  champ géomagnétique, état des bandes, foF2, MUF(3000), MUF du saut, foEs). Panneau propagation,
  fiche QSO (y compris chaque barre Kp), colonne SFI / K du carnet. Attribut title (survol souris).

## Fait — v1.8.0 (21/10/2026) : pages d'agenda historiques
- Déjà en place depuis v0.9 : relevé de propagation hamqsl toutes les 15 min côté serveur (point à chaque
  publication + 1/h), météo si la station est configurée, QSO / écoutes, notes ; navigation par le header.
  Volume estimé ~30 ko/jour (propagation) + ~10 ko/jour (météo, qui fonctionne) : ~15 Mo/an, pas de FIFO nécessaire.
- Ajout : `archive` dans `GET api/day/{day}` (GFZ : 8 Kp, Ap, SFI, SN). Page d'un jour sans relevé
  (historique QRZ depuis 2011) : indices + Kp officiels ; jour avec relevés : Kp définitifs en plus.

## Fait — v1.9.0 (21/10/2026) : le WebSDR comme sonde de propagation (autorun) — supprimé en v1.13.0
- PhantomSDR-ORSAT `autorun/spool.js` : chaque station décodée → `autorun-spots/AAAAMMJJ-HH.jsonl`
  ({t, mode, band, call, grid, snr, f[, dbm]}), indépendamment de l'envoi PSK Reporter / WSPRnet ;
  fichiers > 3 jours effacés par l'autorun (si le carnet ne tourne pas).
- `heard.py` : lecture chaque minute (position mémorisée, ligne incomplète laissée), fichiers lus
  effacés 10 min après la fin de leur heure. Dossier : `<dossier de admin_config.json>/autorun-spots`
  (env `ORSATLOG_SPOTS_DIR`). Table `heard` (une ligne par jour, heure, bande, mode, indicatif ;
  meilleur SNR, nombre de décodages, distance et azimut depuis le locator WebSDR) : **2 ans, plafond
  14 M lignes (~2 Go), FIFO par jour**. Table `heard_sum` (jour, heure, bande, secteur 8 directions :
  stations, distance max) gardée toujours.
- Page d'agenda : « Entendu par le WebSDR » (grille bande × heure, plus lointaines par bande).
  Fiche QSO : stations décodées sur la bande ±1 h (points sur la carte), nombre vers le correspondant
  (azimut ± 30°), plus lointaine dans cette direction, station décodée la plus proche du correspondant.
- Choix F1NSK 21/10 : disque de 232 Go (< 30 Go utilisés) ; taille laissée à mon estimation.

## Fait — v1.9.1 (21/10/2026) : bouton « 📡 Entendu » dans le header
- « Entendu par le WebSDR » s'ouvre à la demande dans une grande fenêtre par-dessus la page (v1.9.2), pour le jour affiché.

## Fait — v1.10.0 (21/10/2026) : carte des stations entendues
- Fenêtre « Entendu » : carte Leaflet (fonds communs `mapbase.js`) de toutes les stations localisées du jour,
  une couleur par bande. Filtres à la souris : boutons de bande, libellé de bande ou case de la grille
  (bande + heure ; la ligne grise est alors dessinée à HH:30). `GET api/day/{day}/heard?band=&hour=`.
- Vérifié dans Chromium avec un faux journal d'autorun (1188 lignes, 5 bandes).

## Fait — v1.10.1 (21/10/2026) : header plus clair
- Bouton Déconnexion retiré (inutile, session de 30 jours ; la route `logout` reste).
- « Carnet / Agenda » remplacé par un choix à deux boutons accolés « 📅 Agenda | 📖 Carnet complet ».
- Raccourcis Alt+← / → / ↓ / C retirés, ainsi que les mentions « Entrée = … · Échap = … » (règle : tout à la souris).

## Fait — v1.11.0 (21/10/2026) : photo, nom et QTH du correspondant (annuaire QRZ)
- `qrzxml.py` : service XML de QRZ (identifiant + mot de passe du compte, pas la clé du logbook) ;
  session gardée, reconnexion si expirée ; réponses gardées 30 jours (table `qrz_lookup`).
  Sans abonnement XML, QRZ peut ne renvoyer qu'une partie des champs (photo comprise) : à vérifier.
- Panneau admin → Carnet ORSAT-LOG → carte QRZ : identifiant et mot de passe, vérifiés avant enregistrement.
- Fiche QSO (pas les écoutes SWL) : photo (clic = agrandie), prénom nom · QTH · pays. `GET api/qrz/lookup/{call}`.
- v1.11.1 / v1.11.2 : indicatif de la fiche = bouton encadré « QRZ ↗ » vers sa page QRZ.com ; message si l'annuaire n'est pas réglé. La fiche est la même depuis l'agenda et le carnet complet.

## Fait — v1.11.4 (21/10/2026) : correctif QSO de groupe
- L'animateur n'était pas enregistré comme contact : il l'est d'office à l'ouverture (et à la modification)
  d'une session, à l'heure de début, fréquence et mode de la session, commentaire « Animateur ».

## Fait — v1.11.5 (21/10/2026) : locator, nom et QTH depuis l'annuaire QRZ à la saisie
- `qrzfill.js` : après 0,7 s de pause dans la frappe d'un indicatif (QSO et QSO de groupe), recherche
  QRZ ; remplit seulement les cases vides (locator `grid`, prénom/surnom, QTH). Indicatif portable
  (EA8/…, …/P) : nom seulement. Groupe : les habitués passent d'abord, QRZ complète. Cache sans `grid` redemandé.

## Fait — v1.12.0 (21/10/2026) : locators manquants des QSO enregistrés
- `qrzxml.GridFiller` : QSO de trafic sans locator, une recherche annuaire QRZ par indicatif (1 s entre
  deux), portables (« / ») ignorés ; locator + distance/azimut mis à jour, **pas renvoyés vers le
  logbook QRZ** (qrz_state inchangé). `GET/POST api/admin/gridfill` ; panneau admin, carte QRZ :
  nombre de QSO sans locator, bouton « Compléter les locators », avancement.
- Formulaire d'édition : bouton « 📇 QRZ » (locator, nom, QTH vides) pour un QSO isolé.
- Limite : le locator QRZ est l'adresse actuelle de la station, pas forcément celle du jour du QSO.

## Fait — v1.12.1 (21/10/2026) : ionosphère d'un QSO récent
- La fenêtre ±2 h ne dépasse plus l'instant présent (fenêtre dans le futur → GIRO répondait 504).
- Serveur GIRO en panne (5xx, délai, réseau) : arrêt après la 1re station, message clair, réessai au ↻.


## Fait — v1.13.0 (23/10/2026) : suppression de l'écoute FT8/WSPR (autorun)
- L'autorun de PhantomSDR-ORSAT chargeait trop le serveur : désactivé côté WebSDR, et fonction
  **supprimée définitivement** du carnet (`heard.py`, boucle de lecture, `api/day/{day}/heard`,
  bouton « 📡 Entendu », fenêtre et carte associées, section « Le WebSDR entendait » de la fiche QSO).
- Au premier démarrage : tables `heard`, `heard_sum`, `heard_spool` supprimées puis `VACUUM`.
- D'autres sources d'analyse de propagation seront étudiées (sans charge sur le PC ORSAT).

## Fait — v1.14.0 (23/10/2026) : météo spatiale, bandes ouvertes, analyse du carnet
Remplace l'écoute FT8/WSPR supprimée : uniquement des sources publiques, quelques requêtes par heure.
PSK Reporter écarté pour l'instant (choix de l'opérateur).
- `spacewx.py` (NOAA SWPC, JSON) : Kp estimé 1 min, Bz/Bt (rtsw_mag_1m, source active), vent solaire
  (rtsw_wind_1m), flux X GOES → classe, éruptions 7 j, échelles R/S/G. Lu par le relevé de 15 min,
  enregistré dans `spacewx` ; éruptions gardées dans `flare` (clé = début). `GET api/spacewx`.
  Page du jour : panneau « Météo spatiale » (direct aujourd'hui, relevés enregistrés les jours passés,
  frise de Bz). Fiche QSO : relevé le plus proche (±30 min) + éruptions de −3 h à +30 min
  (QSO postérieurs à la v1.14 seulement).
- `kc2g.py` (prop.kc2g.com/api/stations.json, ionosondes GIRO/NOAA/INGV/SWS, cache 15 min, mesures
  < 90 min, cs ≥ 25) : grille bandes 160 m–6 m × « proche » (saut 600 km) + 8 directions (saut 3000 km,
  réflexion à 1500 km, MUF(3000) interpolée 1/d² dans 1500 km). Es = 5 × foEs à 1000 km, retenu
  à partir du 17 m. Ouverte < 85 % MUF, limite ≤ 100 %. `GET api/openbands`. Panneau « Bandes ouvertes »
  (page du jour). Limite haute : absorption de jour non comptée. La MUF du trajet d'un QSO reste
  celle de GIRO (fiche QSO, v1.12).
- Vue « 📊 Analyse » (header) : contacts ou écoutes, filtre de bande ; distance médiane / max / part
  > 3000 km selon Kp, SFI et direction (8 secteurs), par heure UTC, grille bande × heure. `GET api/analysis`.
- Vérifié dans Chromium avec des données NOAA / KC2G simulées (bac à sable sans accès à ces sites).

## Fait — v1.15.0 (23/10/2026) : plus de hamqsl.com, indices lus directement à la NOAA
- `solar.py` réécrit : SFI (json/f107_cm_flux.json, mesure la plus récente), K officiel du dernier
  créneau de 3 h et A = moyenne des 8 derniers « a_running » (products/noaa-planetary-k-index.json),
  taches (json/solar-cycle/swpc_observed_ssn.json, lu 2 fois par jour). Champ géomagnétique déduit du K
  (calme / instable / actif / tempête Gn). Même format qu'avant : table `propagation` (source = 'noaa'),
  indices figés à la saisie d'un QSO (solar_src = 'noaa').
- L'état des bandes jour/nuit (formule hamqsl) disparaît : remplacé par « Bandes ouvertes » (ionosondes).
  Les anciens relevés hamqsl restent affichés tels quels sur les jours passés.
- Panneau « Propagation du jour » : SFI, A 24 h, K 3 h, taches. Le X-ray n'est plus qu'en météo spatiale
  (direct) : fin des écarts entre les deux panneaux.

## Fait — v1.16.0 (23/10/2026) : portée par bande (courte / moyenne / longue) et absorption de jour
- `reach.py`, appelé par `kc2g.open_bands` (champ `reach` de `api/openbands`) : par direction, MUF pour
  des sauts de 500 km (réflexion à 250 km), 1500 km (750 km) et 3000 km (1500 km = MUF(3000) mesurée),
  loi de la sécante étalonnée (ionosonde.mufd_estimate). « Zone de silence » = courte fermée, moyenne
  ou longue ouverte.
- Absorption couche D **estimée** (George & Bradley / UIT-R P.533) : A = 677,2·sec(i)·I/((f+1,2)^1,98+10,2),
  I = (1+0,0037R)(cos 0,881χ)^1,3, χ au point de réflexion, R déduit du SFI (NOAA). < 20 dB normale,
  20–40 affaiblie, > 40 absorbée. Nulle de nuit.
- Panneau « Bandes ouvertes » : tableau « Portée par bande » (meilleure direction par défaut ; clic sur un
  en-tête de direction de la grille pour la choisir, re-clic ou ✕ pour revenir). La grille du haut reste MUF seule.

## Fait — v1.16.1 (23/10/2026) : portée en 5 tranches de distance
- `reach.RANGES` : ≤ 100 km (saut 100, NVIS), 100–300 (saut 200, NVIS), 300–900 (saut 600), 900–2500 (1500),
  > 2500 (3000). Zone de silence = « < X km » (borne basse de la première tranche ouverte, toutes les
  précédentes fermées par la MUF). Onde de sol non calculée.

## Fait — v1.17.0 (23/10/2026) : fenêtre « Bandes » depuis le header
- Bouton « 📶 Bandes » dans le header : grande fenêtre (fond assombri, ✕ ou clic à côté pour fermer, ↻ pour
  recalculer) avec côte à côte la grille par direction et la portée par bande. Plus dans la page du jour.
- Météo spatiale déplacée dans la colonne gauche, sous « Propagation du jour ».

## Fait — v1.18.0 (23/10/2026) : carte azimutale des zones de silence
- `reach.skip_map` : azimuts tous les 10°, 40 anneaux (50 km jusqu'à 1000 km, puis 200 km jusqu'à 5000 km).
  Saut unique jusqu'à 3500 km, au-delà n sauts égaux (MUF = la plus basse des deux réflexions extrêmes,
  absorption cumulée). État codé une lettre par case et par bande (o/e/w/a/c/-). Cache 15 min dans
  `kc2g.skip_map`. `GET api/skipmap` ajoute les correspondants du jour ayant une position (locator ou QRZ).
- `SkipMap.svelte` (fenêtre « 📶 Bandes ») : projection azimutale équidistante centrée sur le QTH (d3-geo,
  fond Natural Earth `world-atlas` 110m embarqué), choix de la bande à la souris, correspondants du jour
  placés avec leur état (silence / ouvert…) sur leur bande, liste triée par distance, détail au survol.
- À venir : choix de la meilleure antenne (inventaire à saisir, dont loops onde entière horizontales).

## Fait — v1.18.1 (23/10/2026) : carte et portée par bande sur un seul calcul
- `reach.build_grid` (azimut 5°, anneaux 50 km jusqu'à 1000 km puis 250 km, distance réelle de chaque
  anneau) partagé par `skip_map` et `compute` ; grille en cache dans `kc2g._grid` (renouvelée avec les mesures).
- Tableau : état d'une tranche = celui qui en couvre la plus grande part sur la direction (cases sans mesure
  ignorées s'il y a mieux) ; silence = bord intérieur du premier anneau ouvert. Ligne « meilleure direction » :
  plus petite zone de silence, sauf si une direction passe dès le QTH.

## Fait — v1.19.0 (23/10/2026) : zoom de la carte et meilleure antenne
- Carte : zoom à la molette (centré sur le QTH, 150 à 5000 km) et boutons 250 / 600 / 1200 / 2500 / 5000 km ;
  anneaux repères adaptés au zoom ; fond de carte 1:50 M chargé à la demande sous 1500 km. Grille plus fine
  près du QTH : anneaux de 25 km jusqu'à 300 km.
- `antennas.py` : 19 modèles types (dipôles 6/10/15/25 m, V inversé, EFHW, NVIS 3 m, loops onde entière
  horizontales 7 et 15 m, delta-loop verticale, verticales λ/4 et 5/8 au sol, ground-plane surélevée, loop
  magnétique, hexbeam, Yagi 3 él. 12/20 m, Yagi 5 él., quad 2 él.). Gain = espace libre + diagramme vertical
  + image dans un sol moyen (Fresnel, εr 13, σ 5 mS/m) ; verticales au sol : diagramme sol parfait × |1+Γv|/2.
  Angle de départ par tranche (F2 à 300 km ; DX : 2 à 8°). Classement fixe par bande/tranche, en cache.
- Fenêtre « Bandes » : tableau « Meilleure antenne » (là où la bande passe, direction choisie ou meilleure),
  bouton pour exclure les antennes directives, top 4 au survol.
- À faire éventuellement : marquer « mes antennes » pour ne classer que celles de la station.

## Fait — v1.19.1 (23/10/2026) : carte plus détaillée au zoom
- Fond Natural Earth 1:10 M (`world-atlas/countries-10m`, ~1 Mo compressé) chargé seulement sous 600 km.
- Villes : `frontend/src/data/cities.json` (5764 lieux ≥ 15 000 hab., extraits de ne_10m_populated_places_simple,
  domaine public ; [nom, lat, lon, population], trié par population). Chargé sous 2500 km ; seuil de population
  selon le zoom (3 M → 15 000), 70 noms au plus, sans chevauchement, indicatifs des correspondants prioritaires.
- Fusion avec PhantomSDR-ORSAT écartée (dépôts séparés : suivi de PhantomSDR-Plus, techniques différentes).

## Fait — v1.19.2 (23/10/2026) : correctif de mise à jour
- `.gitignore` : `data/` excluait aussi `frontend/src/data/cities.json` (compilation en échec sur le serveur,
  « Could not resolve './data/cities.json' »). Règle limitée à la racine : `/data/` (base et sauvegardes).

## Fait — v1.20.0 (23/10/2026) : vue satellite de la carte des zones de silence
- `GET api/sattile/{z}/{y}/{x}.jpg` : tuiles Sentinel-2 cloudless 2017 (EOX, CC BY 4.0, WMTS
  s2cloudless-2017_3857, Web Mercator) téléchargées par le carnet et gardées dans `data/tiles/`
  (même origine pour la page, pas de nouveau téléchargement d'une zone déjà vue).
- `frontend/src/satellite.js` : reprojection pixel par pixel en azimutale équidistante (projection inverse
  d3-geo → pixel Mercator), à 2× la résolution affichée, niveau de tuiles selon l'échelle (2 à 13),
  recalcul 250 ms après un zoom. Bouton « Vue carte / Vue satellite » ; zones colorées plus transparentes
  sur l'image. Vérifié avec des tuiles de test (bac à sable sans accès à EOX).
- Plus aucun avertissement à la compilation (sélecteurs CSS inutiles, rôles ARIA, seuil de taille relevé).

## Fait — v1.20.1 (23/10/2026) : molette sur la carte
- Svelte 5 pose « onwheel » en écouteur passif : preventDefault ignoré, la fenêtre défilait au lieu de zoomer.
  Écouteur `wheel` posé à la main avec { passive: false } (SkipMap.svelte). Vérifié : 4 crans = 5000 → 2000 km,
  fenêtre immobile.

## Fait — v1.20.2 (23/10/2026) : molette sur la carte (Firefox)
- Firefox garde la molette sur l'élément qui défilait (« wheel transaction ») : l'écouteur de la carte ne
  recevait rien juste après un défilement de la fenêtre. Écouteur `wheel` sur window (capture, non passif) :
  zoom dès que le pointeur est dans le cadre de la carte, quel que soit l'élément visé.
  Pas de Firefox dans le bac à sable (téléchargement bloqué) : testé sous Chromium, à confirmer sous Firefox.

## Fait — v1.21.0 (23/10/2026) : zone d'écoute du WebSDR (carte + page publique)
- Antenne du WebSDR simulée avec NEC-2 (PyNEC, sol de Sommerfeld) : loop horizontale 80 m de périmètre,
  légèrement trapézoïdale (modèle 25/15/20/20 m), 6 m au-dessus d'un sol sablonneux (εr 5, σ 1 mS/m),
  alimentée dans un angle par un balun 4:1. `backend/orsatlog/websdr_loop.json` : par bande, gain moyen
  par degré d'élévation (« avg »), grille complète élévation × azimut 5° (« grid », pour une future
  orientation), impédance, désadaptation / 200 Ω, pénalité S/B (désadaptation au-delà de la marge de bruit
  extérieur UIT-R P.372 rural : nulle partout).
- `reach.listen_map` : là où la bande passe, gain de la loop à l'angle d'arrivée (−3 dB en limite de MUF,
  −6 dB si affaiblie) → G bonne (≥ 0 dBi) / M moyenne (≥ −6) / P faible ; grille propre au locator du
  WebSDR (`swl_locator`), grilles en cache par locator. `GET api/listenmap` (connecté),
  `GET api/public/listenmap` (sans connexion, aucune donnée du carnet).
- Carte : bouton « Émission station / Écoute ORSAT ». Page publique `/ecoute` (https://orsat.ddns.net/log/ecoute) :
  carte d'écoute seule, sans correspondants ni image satellite ; publics : /ecoute, /assets/*,
  api/public/listenmap. Vérifié : carnet, réglages, cartes privées et tuiles restent en 401 sans connexion.
- À faire : bouton sur la page du WebSDR (dépôt PhantomSDR-ORSAT) ouvrant /log/ecoute ; orientation de la loop.

## Fait — v1.21.1 (23/10/2026) : probabilité de réception pour le bandeau du WebSDR
- `GET api/public/listenbanner?radius=800` (public) : par bande, % pondéré par la surface dans le disque
  autour du WebSDR (bonne 1 / moyenne 0,6 / faible 0,25 / silence ou absorbée 0 ; cases sans mesure écartées).
  Utilisé par le bandeau de PhantomSDR-ORSAT (même origine : /log/api/public/listenbanner).

## Fait — v1.22.0 (23/10/2026) : mesure réelle du WebSDR (SNR) et étalonnage de la prévision
- `snr.py` : connexion locale à la chute d'eau de PhantomSDR-ORSAT (ws://127.0.0.1:<port>/waterfall, port lu
  dans config.toml à côté d'admin_config.json). Toutes les 5 min, ~3 s par bande amateur (commande « window ») ;
  lignes zstd → CBOR {l, r, data int8 en dB}. Par bande : bruit (20e centile du spectre moyen en puissance),
  signaux (groupes ≥ 10 dB au-dessus du bruit), meilleur SNR, occupation (≥ 6 dB). Aucun décodage ni son.
  Dépendances : zstandard, cbor2.
- Table `snr_obs` (gardée 400 jours) : mesure + couverture prévue au même moment (`reach.listen_probability`).
  `db.snr_calibration` : par tranche de couverture (70–100, 40–70, 15–40, 0–15 %), part des mesures avec un
  signal exploitable (SNR ≥ 10 dB), sur 30 jours.
- `api/public/listenbanner` ajoute `measured` (dernière mesure) et `calibration`. `api/info` : état de la mesure.
- Bandeau PhantomSDR-ORSAT : verdict en clair pour la bande écoutée (Fiable ≥ 70 / Correct ≥ 40 / Aléatoire ≥ 15
  / Fermé), mesure réelle à côté, étalonnage constaté dans l'infobulle (affiché à partir de 30 mesures par tranche).
- Vérifié avec un faux WebSDR parlant le même protocole (signaux injectés à 12, 18 et 30 dB retrouvés).

## Fait — v1.22.1 (23/10/2026) : page publique « écoute » en FR / EN / ES
- `frontend/src/ecouteI18n.js` : textes de la page publique et de la vue écoute de la carte ; langue lue dans
  `?lang=fr|en|es` (passée par le bandeau du WebSDR selon la langue de l'auditeur). Le carnet reste en français.

## Fait — v1.23.0 (24/10/2026) : indice de performance (IP) du WebSDR
- `reach.performance_index` : par bande, note de chaque tranche (≤100, ≤300, ≤900, ≤2500, >2500 km ; cases pondérées
  par la surface dans la tranche) ; prévision = 0,7 × meilleure tranche + 0,3 × moyenne ; zone = tranche la mieux
  notée si ≥ 50 (loc / reg / eu / dx). Mesure réelle (snr.py, < 15 min) : 70 × SNR (6→30 dB) + 30 × signaux (→10) ;
  IP = 0,4 × prévision + 0,6 × mesure, sinon prévision seule.
- `api/public/listenbanner` : champ `ip`, `measure_error` (cause d'une mesure absente). L'étalonnage (`snr_obs.pred_pct`)
  porte désormais sur la prévision de l'IP.

## Fait — v1.27.0 (26/10/2026) : orages sur la carte et analyse du bruit
- Carte de la fenêtre « Bandes » (carnet, pas la page publique) : cellules orageuses des 30 dernières min (carrés de 0,5°),
  taille selon le nombre d'impacts, couleur selon l'âge (rouge < 10 min, orange < 20, jaune < 30), infobulle,
  bouton « Orages affichés / masqués ». Rafraîchi chaque minute.
- Analyse, nouvel onglet « Bruit / QRN » (`GET /api/analysis/qrn?days=`, `qrn.py`) : écart moyen du bruit de fond
  (160/80/40/20/10 m) au bruit habituel de la même heure UTC, selon foudre < 500 km, < 2000 km, activité mondiale
  (terciles), Kp et tendance de pression 3 h. Périodes 30 j / 90 j / 1 an. Case vide = moins d'une heure de mesures.
- Les classes ne deviennent parlantes qu'après quelques semaines d'enregistrement de la foudre (depuis le 26/10/2026).

## Fait — v1.26.0 (26/10/2026) : orages (Blitzortung) et QRN
- Écoute permanente du flux public Blitzortung.org (`lightning.py`, WebSocket ws1/ws7/ws8, décodage LZW de la carte).
  Rien de brut stocké : comptage par tranche de 5 min (monde, < 500 km, < 2000 km, 8 secteurs, impact le plus proche)
  → table `lightning` (400 jours). Impacts des 30 dernières min (< 3000 km) gardés en mémoire pour la carte.
- Centre des distances : locator SWL (récepteur ORSAT), sinon locator de la station.
- Le bruit de fond par bande existait déjà (mesure réelle v1.22, table `snr_obs`, 10 bandes) : réutilisé, rien de mesuré en plus.
  Nouveau : écart au bruit « habituel » (médiane des 30 derniers jours à la même heure UTC).
- `GET /api/lightning` : 15 dernières min + bruit actuel et son écart ; `GET /api/day/{jour}` : `lightning` et `noise`.
- Panneau « Orages et QRN » (page du jour, colonne droite) : orage le plus proche, rose des 8 secteurs, comptages,
  écart de bruit 160/80/40/20/10 m, courbe 24 h foudre (barres) + bruit 160/80/40 m (lignes).
- Réglage `blitzortung` (1 par défaut, 0 = coupé sans redémarrage) : interrupteur à ajouter dans le panneau admin ORSAT.
- Non testé en réel depuis l'atelier de Claude (Internet bloqué) : à vérifier sur le PC ORSAT.

## Fait — v1.25.1 (25/10/2026) : logo ORSAT-LOG
- Logo « carnet ouvert » (`docs/branding/orsat-log-icon.svg`), même famille que celui d'ORSAT SDR.
- Icônes d'onglet (SVG, PNG 32/192/512, apple-touch, favicon.ico) dans `frontend/public/`, publiques ;
  logo dans l'en-tête du carnet et sur la page de connexion.

## Fait — v1.25.0 (25/10/2026) : absorption de la couche D mesurée
- `backend/orsatlog/dlayer.py`. Le modèle George & Bradley (soleil calme) est désormais corrigé par la mesure :
  1. **Éruptions** : flux X GOES en temps réel, modèle D-RAP NOAA (HAF = 10·log10(flux) + 65 MHz au point
     subsolaire, × cos(χ)^0,75 ; (HAF/f)^1,5 dB par traversée × sécante), à partir de C1.
  2. **fmin des ionosondes** (GIRO, getbest `fmin,foF2`) : Roquetes, El Arenosillo, Dourbes, Rome, Chilton,
     Fairford, Pruhonice, Gibilmanna. Facteur (fmin / médiane des 15 jours à la même demi-heure)², borné
     0,5–8, interpolé (1/d², 1500 km) ; ionogramme de jour sans aucun écho = black-out (×8) ; nuit = ×1.
     Relevé toutes les 15 min (16 jours d'historique au premier passage). Sans données : facteur 1.
  3. Case sans MUF (ionosonde muette) mais absorption mesurée > 40 dB : « absorbée » et non plus « pas de mesure ».
- Affichage : ligne « Couche D mesurée » dans la météo spatiale (facteurs par station, infobulle détaillée,
  éruption en cours) ; bandeau d'alerte dans la fenêtre Bandes quand l'absorption est renforcée.
- Effet voulu sur la prévision de l'IP (plus juste pendant les éruptions) ; la mesure SNR n'est pas touchée.
- À vérifier sur le serveur : que GIRO publie bien la fmin de ces stations en temps quasi réel (infobulle).

## Fait — v1.24.0 (24/10/2026) : conseil de partenaire pour la diversité du WebSDR
- `backend/orsatlog/partners.py`, route publique `/api/public/diversity` (sans connexion).
- Partenaires lus dans `diversity_partners.json` de PhantomSDR-ORSAT (rubrique admin « Réception en diversité »),
  liste par défaut sinon. Pour chaque bande : part (pondérée par la surface, jusqu'à 3000 km) de la zone entendue
  par ORSAT que le partenaire entend aussi (cartes des zones de silence depuis les deux locators, mêmes
  ionosondes KC2G, propagation seule) × facteur d'éloignement (0 sous 100 km, 1 dès 300 km).
  ≥ 55 % et meilleur : « ★ Conseillé » ; ≥ 30 % : « Possible » ; sinon « Peu utile ». Cache 10 min.
- Disponibilité : chaque partenaire sondé toutes les 10 min (page d'accueil, /status pour un KiwiSDR) ;
  hors ligne = jamais conseillé, carte grisée sur le WebSDR.
- **Séparé de l'IP d'ORSAT** : lecture seule des cartes de propagation, rien en base, rien dans
  performance_index ni la mesure SNR.
- À venir (étape 2) : statistiques réelles des séances de diversité (part du temps sur le partenaire, gain de SNR,
  échecs) envoyées par le WebSDR, puis mêlées à la prévision.

## Fait — v1.23.1 (24/10/2026) : mesure réelle — recherche automatique de la chute d'eau
- Sur le serveur, `[Errno 111] 127.0.0.1:9001` : le port de spectrumserver n'est pas celui de config.toml.
  `snr.waterfall_candidates()` reprend l'ordre du proxy de PhantomSDR-ORSAT : station.conf (PORT_SDR), puis
  admin_config.json (public_port, sdr_host, prioritaire), puis config.toml, puis le port public du proxy
  (proxy_port, qui relaie /waterfall), puis 9001. La première adresse qui répond est retenue (`url_ok`).
## Deux PC (question F1NSK 20/10) — sans objet depuis le serveur central
- Code : aucun souci (GitHub). 2e PC = clé SSH sans phrase de passe + `git clone` + `./update.sh` une fois.
- **Données : base SQLite locale à chaque PC → carnets divergents.** Solutions proposées, choix en attente :
  dossier synchronisé (Syncthing/Nextcloud, jamais les deux PC ouverts en même temps) /
  sauvegarde-restauration complète dans les Réglages / un PC serveur accessible à distance.

## À faire (ordre proposé)
1. ~~Import ADIF~~ (v1.2.0, retiré en v1.3.1 au profit de la synchronisation QRZ.com).
2. ~~Édition d'un QSO existant~~ (fait en v0.7.0).
3. Onglet **Analyse** : QSO par bande × heure UTC, carte des contacts (grand cercle depuis le QTH),
   distances max par bande, corrélation avec SFI/K.
4. Recherche / filtres dans le carnet (indicatif, bande, mode, période).
5. Préfixes → pays DXCC (cty.dat) et entité dans chaque QSO.
6. Spots TCI / DX cluster, croisement RBN / PSKReporter.
7. Envoi de commandes TCI (cliquer un spot = changer de fréquence).
8. ~~QRZ~~ (fait v1.3.0).
9. Suite fiche QSO : météo pour la VHF. (Éruptions X : fait v1.14.0.) LoTW / eQSL — **uniquement des contacts** (jamais les SWL).

## Sources TCI visées
- **AetherSDR** (serveur TCI v2.0 : CAT, audio, IQ, CW, spots, événements récepteur ; FlexRadio en priorité,
  aussi récepteurs en réception seule). Port 50001 (applet « TCI Server » d’AetherSDR, à démarrer).
- **WebSDR ORSAT** (page du navigateur, CAT Sync) : fait en v0.6.0, ORSAT-LOG = serveur TCI sur 40001.
- **Orsat-SDR** (plus tard) pour les logs SWL → nécessite d'ajouter un serveur TCI dans Orsat-SDR.

## Mode SWL — suite
- Fait en v0.3 : saisie de base (voir plus haut).
- À faire : identification automatique de la station par fréquence + heure via une grille de diffusion (EiBi)
  → émetteur et distance connus sans saisie : très utile pour l'analyse de propagation.
