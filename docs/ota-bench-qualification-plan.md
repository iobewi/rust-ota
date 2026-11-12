# Qualification OTA par le banc IOBEWI — préparation

## Révisions figées pour l'inspection du 2026-11-04

- rust-ota main: `20d8a6601664b746c914fc887c67d712efe50b2a`.
- rust_dev PR #4, branche `feat/bench-pytest-runner`: `54c69ecc2bbbbd95d682301a8017e18ccb371a51`, non fusionnée.
- Le banc expose les opérations matérielles via navigateur Web Serial → serveur API → client Python. pytest seul décide du verdict.
- Aucun équipement n'a été contacté lors de cette préparation. État courant, epoch, génération, capacité, RDID, partitionnement et provenance du port : **non observés**.

## Périmètre des recettes ajoutées

`tests/ota_bench/` utilise le client/les preuves de `iobewi_bench.qualification.Campaign`, sans moteur de test ni transport série ajouté.

- `test_bench_identity_and_target` : précontrôle connecté/libre/non-quarantaine/sans grant par Campaign et identification MCU par API.
- `test_partition_geometry_explicit_opt_in` : lecture/décodage de table seulement si l'adresse a été déterminée indépendamment et fournie explicitement.
- Les deux recettes sont SKIP sans `--bench`. **Aucun test OTA, image A/B ni scénario d'écriture n'est ici déclaré couvert.**
- Attention : certaines opérations chargeur peuvent redémarrer la carte même en lecture seule.

## Installation et lancement (sur machine ayant accès au serveur)

Installer la dépendance depuis la PR non fusionnée, sur son SHA exact (exemple de clone séparé):

```sh
git clone https://github.com/iobewi/rust_dev.git /private/rust_dev-bench
git -C /private/rust_dev-bench checkout 54c69ecc2bbbbd95d682301a8017e18ccb371a51
python -m pip install -e '/private/rust_dev-bench/bench/python[pytest]'
python -m pytest tests/ota_bench -q  # SKIP matériels sans opt-in
```

Ne pas mettre les tokens dans les commandes. Sur l'hôte du banc, après lecture seule autorisée :

```sh
umask 077
export BENCH_URL=http://127.0.0.1:8080
export BENCH_DEVICE=esp32-local
export OTA_EXPECTED_CHIP=esp32c3
# export BENCH_CLIENT_TOKEN via un mécanisme privé
python -m pytest tests/ota_bench -k identity --bench \
  --bench-results /private/ota-qualification/preflight \
  --junitxml=/private/ota-qualification/preflight.xml -v
```

Le plugin utilise `--bench-device` et `--bench-url` ou les variables ci-dessus. Ne définir `OTA_PARTITION_TABLE_OFFSET` qu'après détermination indépendante de l'adresse; la valeur 0x8000 dans le CSV de l'exemple n'est pas une mesure sur la carte.

## Contrat firmware système à qualifier

`examples/ota-system` fournit, selon le profil de compilation, les routes TLS `GET /health`, `POST /ota/upload`, `POST /ota/activate`. `/health` renvoie seulement `ok`, sans version/slot/probation. La confirmation est interne au self-check; les logs UART rendent notamment `boot: running ... status ...` et `confirmed`/`stable`. Cela ne remplace pas la relecture durable des partitions et métadonnées.

- Upload : `X-Deployment-ID`, `X-Image-SHA256`, corps binaire ESP et, si profil signé, `X-Image-Manifest`; statut 200 `staged` après validation/publication.
- Activation : même deployment ID, corps vide, manifeste à nouveau si requis; statut 200 `activating`, reboot; un résultat réseau perdu n'est pas un refus prouvé.
- Profil non signé par défaut : intégrité sans preuve cryptographique d'éditeur.
- `signed` : ECDSA P-256 IAM1; `signed-rsa` : RSA-PSS 3072 et preuve IAP1. Les clés de test restent privées et distinctes des clés de production.
- Boot A/B : metadata `BOOT` v2, états New/PendingVerify/Valid/Invalid/Aborted. Ne pas présumer qu'une image de repli restera utilisable après une écriture interrompue.
- `ota_meta` (OTM1) et `otadata` sont des régions distinctes.

## Matrice de préparation

| ID | Scénario | Précondition / action | Assertion et preuve requises | Statut |
| --- | --- | --- | --- | --- |
| P0 | Connexion / génération | API disponible, carte libre; identifier | snapshot epoch/generation, identify, cleanup | NON EXÉCUTÉ |
| P1 | Partitions | Offset indépendant vérifié; parser | labels, offsets, bornes, hash table et sauvegarde | NON EXÉCUTÉ |
| P2 | Baseline flash | Cible et taille confirmées; dump complet | SHA-256, sauvegarde privée, restauration vérifiable | NON EXÉCUTÉ |
| O1 | Image B valide | A confirmée, image/signature compatible; upload | 200 staged, digest/proof/OTM1 et slot inactif relus | NON EXÉCUTÉ |
| O2 | Activation B | B publiée; activate/reboot | New → PendingVerify → Valid, identité B et confirmation durable | NON EXÉCUTÉ |
| O3 | Retour A | Image A distincte compatible; upload/activate | identité A, données conservées, preuves relues | NON EXÉCUTÉ |
| O4 | Manifeste invalide | Profil signé actif; upload | refus précis, aucune activation, preuves avant/après | NON EXÉCUTÉ |
| O5 | Image tronquée | B et sauvegarde validées; transfert incomplet | refus, preuve invalide, disponibilité fallback mesurée | NON EXÉCUTÉ |
| O6 | Self-check rejeté | Image de défaut distincte, fallback confirmé | rollback observé et métadonnées cohérentes | NON EXÉCUTÉ |
| O7 | Absence confirmation | Timeout/WD armé, fallback utilisable | candidate abandonnée, retour au slot Valid | NON EXÉCUTÉ |
| O8 | Interruption transfert | Scénario borné, restauration disponible | contrat de reprise/abandon et état durable observés | NON EXÉCUTÉ |
| O9 | Coupure écriture | Autorisation spécifique supplémentaire | ancien/nouveau état, aucune activation partielle | NON EXÉCUTÉ |

**Bloquants avant écriture** : accès API réel non démontré; identification flash RDID/capacité/partitionnement non démontrée; pas de firmware A/B prêt ni signature de test produite; aucune sauvegarde privée complète vérifiée; diagnostic HTTPS ajouté sous feature qualification (build + MAC + slot + BOOT v2), restant à qualifier sur C3; OTM1 décodé séparément dans les recettes depuis la flash. Proposer au besoin une route diagnostique read-only authentifiée ou des marqueurs UART structurés avec relecture des métadonnées; documenter précisément leur provenance.

## Autorisation à recueillir après préparation, avant première écriture

Présenter : identifiant carte + génération/epoch; RDID/capacité; carte de partition et chevauchements; hashes de la sauvegarde intégrale et régions privées; plan de restauration avec outil, accès ROM vérifié et hashes attendus; SHA des firmwares et bootloader; IDs A/B, versions, profils et manifests; plages exactes que la première installation pourra effacer/écrire; liste des tests destructifs et conditions d'arrêt.

Ne jamais flasher un CSV supposé, écraser des secrets privés, lever une quarantaine, ni provoquer de coupure durant une écriture sans autorisation dédiée. Le plan `prepare.py` d'un profil 4 Mio est une proposition de partitionnement, pas une approbation de programmation.
