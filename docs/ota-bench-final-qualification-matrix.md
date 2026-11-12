# Recette matérielle finale — rust-ota sur IOBEWI Device Lab

Référence de préparation : branche `test/ota-bench-pytest-preparation`. Cette matrice est un **contrat de qualification**, pas un compte rendu de matériel. Les verdicts initiaux sont `NOT_RUN`. `main` est considéré figé : aucune correction du moteur OTA ou du banc générique n'entre dans le périmètre. Les seules exceptions nécessitent une nouvelle décision explicite si une recette révèle un défaut bloquant.

## Profils et portée

- **S3 wide, RSA** : OTA système A/B, VerifiedBoot logiciel avec IAP1 RSA-PSS 3072, refus et repli, panic/watchdog, supervision B (si binaire correspondant).
- **S3 P-256** : admission/activation IAM1 ECDSA P-256 ; ne pas le confondre avec la validation RSA/IAP1 du boot.
- **C3** : cible 4 Mio, OTA A/B et fonctions de boot réellement disponibles. Ne jamais transférer automatiquement un verdict S3 à C3.
- **Non revendiqué** : eFuses, Secure Boot V2 matériel, flash encryption, anti-rollback protégé, rotation dynamique persistante de clés, ou comportement de coupure non observé. Les contrats logiciels #15/#16 ne sont pas un backend protégé intégré.

## Matrice de tests

| ID | Cible | Stimulus | Assertion de qualification | Recette/état |
|---|---|---|---|---|
| PRE-01 | S3+C3 | identify, table de partitions | puce/capacité mesurées, géométrie explicite, aucune écriture | `test_preflight.py`, à jouer |
| PRE-02 | S3+C3 | sauvegarde flash intégrale + boot ROM de restauration | 2 lectures cohérentes, SHA-256 et stockage persistant privé, retour ROM démontré | procédure prérequis, à automatiser |
| SYS-01 | C3 | upload B signé en A confirmé | B digest indépendant et OTM1 Written ; A reste exécutée | `test_staged_image.py`, à jouer |
| SYS-02 | C3 | activation de B préalablement staged | B exécutée, BOOT Valid durable, OTM1 finalisé, A préservée | `test_activation.py`, à jouer |
| SYS-03 | C3 | B→A avec nouveau staging et nouveau plan | retour A, fallback B confirmé, identité et stockage cohérents | réutilisation paramétrée des recettes, à jouer |
| SYS-04 | S3+C3 | reset d'une image stable confirmée | même build/slot et mêmes secteurs BOOT/OTM1 après démarrage | `test_stable_reset.py`, à jouer |
| SYS-05 | S3+C3 | image tronquée / mauvais digest | refus observé, absence de nouvelle activation, relecture OTM1/BOOT | recette de stimulus manquante |
| SYS-06 | S3+C3 | mauvais deployment ID, jeton absent/faux, requête incohérente | code HTTP exact ; aucune mutation durable | assertions hôte présentes ; recette matérielle à compléter |
| SYS-07 | S3+C3 | interruption pendant upload | aucun succès déduit d'une coupure transport ; état réel après reboot et récupération | à développer |
| SYS-08 | S3+C3 | self-check explicitement rejeté | Invalid/Aborted, authentique fallback exécuté, identité vérifiée | analyse forensic présente ; injection à développer |
| SYS-09 | S3+C3 | hang PendingVerify / timeout | rollback effectif, cause de reset attribuée, jamais confirmé | à développer |
| SYS-10 | S3+C3 | panic Stable et PendingVerify | reset borné, comportement Stable vs probation documenté | à développer |
| BOOT-01 | S3 | image et IAP1 valides RSA | démarrage vérifié et preuve lue indépendamment | à développer |
| BOOT-02 | S3 | image modifiée / IAP1 absent, tronqué, invalide ou clé étrangère | refus spécifique, repli authentique ; aucune promotion | à développer |
| BOOT-03 | S3 | aucun slot authentique | HALT explicite, aucune réparation/formatage silencieux, restauration prouvée | à développer, destructif |
| BOOT-04 | S3 | fallback inverse ota_1→ota_0 | VerifiedBoot et relecture des deux copies BOOT | à développer |
| AUTH-01 | S3 | IAM1 ECDSA P-256 valide puis fautes de signature/cible/digest | admission conforme et refus sans publication | à développer |
| SUP-01 | S3 | OTA composant B, A en service | staging/activation sans reset A, confirmation, isolation partitions | à développer |
| SUP-02 | S3 | B panic, ignore-stop, log-flood, reset-chip | stop/rollback/garde anti-boucle, A reste disponible | à développer |
| SUP-03 | S3 | reset en Staged/Activating/PendingConfirmation/rollback B | reprise déterministe, pas de métadonnées inconnues réinitialisées | à développer |
| CUT-01 | S3 | coupure physique erase/write du slot inactif | aucun boot d'image partielle ; lecture indépendante des images/proofs | **BLOCKED** sans dispositif coupure contrôlée |
| CUT-02 | S3 | coupure IAP1/OTM1/BOOT/confirmation | ancien/nouveau/erreur explicite, repli ou HALT ; jamais false PASS | **BLOCKED** sans dispositif coupure contrôlée |
| SEC-01 | S3+C3 | requêtes administrateur sans jeton, vide, erroné | refus non ambigu, sans mutation avant authentification | lecture/contrats existants ; essais matériels à compléter |
| END-01 | S3+C3 | restaurer baseline approuvée et relire | SHA-256 des plages restaurées identiques, fonctionnement et release du banc | procédure et preuve manquantes |

Les essais déjà acquis dans les campagnes historiques restent traçables ; ils ne deviennent pas automatiquement PASS pour ce nouveau SHA ou ce nouveau banc. Les différences de prise en charge par MCU doivent être déclarées `NOT_APPLICABLE` avec justification documentée, jamais converties en PASS.

## Ordre d'exécution

1. **Audit de la branche** : tester la cohérence des fixtures, corrigés éventuels de recette uniquement, vérifier le SHA exact et la CI. Revoir explicitement les modifications firmware déjà présentes sur la branche, sans les intégrer tacitement dans `main`.
2. **Lecture seule** : PRE-01, PRE-02 et captures diagnostiques ; confirmer puce, RDID, flash, géométrie, backup exact, cartographie et liaison HTTPS ↔ MAC via le banc.
3. **Nominal C3** : SYS-01, SYS-02, SYS-04, SYS-03 ; plans et approbations distincts pour staging et activation. Ne pas rejouer après résultat inconnu.
4. **Nominal S3** : RSA VerifiedBoot et P-256, A/B nominal, redémarrage stable, B supervisé ; obtenir preuves nouvelles et distinctes.
5. **Refus/pannes** : mauvais manifests, upload interrompu, self-check, watchdog et panic ; isoler une fenêtre de preuve et restaurer avant le scénario suivant.
6. **Coupures** : ne commencer CUT-01/02 qu'après ajout et revue d'un équipement électrique capable de couper pendant une phase identifiée, avec mesure de l'alimentation et contrôle du risque d'usure.
7. **Bilan** : matrice PASS/FAIL/BLOCKED/INDETERMINATE/NOT_APPLICABLE, rapports JUnit, relectures, restauration et décision de clôture.

## Exigences de preuve

Chaque essai : SHA des sources de recette et des binaires, révision du banc et du firmware, epoch et génération du device, identité MCU/RDID/capacité, offset réel de table, image et manifeste hashés, préconditions, consentement, fenêtre UART bornée, requête/réponse HTTP avec secrets expurgés, dump indépendant avant/après avec SHA-256, BOOT v2 et OTM1 décodés, slot réellement exécuté, cause de reset quand pertinente, verdict et restauration exacte.

Conserver les dumps, backups, tokens, grants, certificats privés, logs bruts et manifests d'approbation **hors Git** sur support persistant vérifié. Un appel HTTP 200, un CRC ou un message UART ne suffit jamais isolément à établir une preuve d'authenticité ou de persistance. Une interruption de transport, d'epoch ou de génération clôt la fenêtre de preuve ; aucune écriture/reset automatique pour lever une issue indéterminée.

## Nouveau cas SYS-04 : reset Stable

Fichier : `tests/ota_bench/test_stable_reset.py`. Pas d'upload, pas d'effacement : reset explicitement autorisé puis relecture BOOT/OTM1 et vérification TLS du binaire exécuté.

Plan privé d'exemple, **valeurs à remplacer par mesures effectives** :

```json
{
  "schema": 1,
  "scope": "ota.stable-reset-persistence",
  "device": "esp32-local",
  "mcu": "esp32c3",
  "flash_size": 4194304,
  "table_offset": 32768,
  "otadata_offset": 53248,
  "ota_meta_offset": 61440,
  "expected_build_id": "qualification-B-001",
  "expected_slot": 1
}
```

Lancement une fois le plan et son empreinte approuvés :

```sh
export OTA_STABLE_RESET_PLAN=/private/ota/stable-reset.json
export OTA_STABLE_RESET_PLAN_SHA256=<empreinte SHA-256 exacte>
export OTA_APPROVED_STABLE_RESET=yes
# BENCH_URL, BENCH_DEVICE, BENCH_CLIENT_TOKEN,
# OTA_HTTPS_ORIGIN, OTA_CA_FILE, IOBEWI_OTA_TOKEN privés
python -m pytest tests/ota_bench/test_stable_reset.py --bench \
  --bench-results /private/ota/evidence/stable-reset \
  --junitxml=/private/ota/evidence/stable-reset.xml -v
```

Le reset nécessite un accord spécifique, même s'il ne contient aucun flash.write. Le test attend un firmware déjà Stable. Le reset est envoyé une seule fois ; perte d'accusé ou état indéterminé bloque toute continuation automatique.

## Règles de développement

Les recettes métier restent dans `rust-ota/tests/ota_bench` et utilisent `iobewi_bench` sans créer de deuxième transport, protocole ou runner. Les scénarios absents sont à implémenter, pas à marquer réussis. Préparer une PR, exécuter les tests hôte de **recette**, faire relire le SHA exact indépendamment, puis seulement solliciter la validation opérateur avant les essais matériels. Aucun test matériel, aucune fusion, aucune clôture d'issue n'est autorisé par la seule rédaction de ce plan.
