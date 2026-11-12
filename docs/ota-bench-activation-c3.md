# Activation OTA A/B sous approbation distincte — ESP32-C3

## Préparation

`tests/ota_bench/test_activation.py` est une recette de **qualification matérielle non exécutée**.
Elle n'a aucun mécanisme de reprise automatique après un POST `/ota/activate`
indéterminé. Le test suppose une candidate déjà publiée et vérifiée séparément
par `test_staged_image.py`, puis un nouvel état flash sauvegardé et approuvé.

Les préconditions doivent être vérifiées avant de demander l'autorisation :
- C3 réelle, capacité flash confirmée, table de partitions observée.
- A actuellement `Valid`, B intégralement écrite et signée conformément au
  profil effectivement actif.
- Diagnostic `qualification-diagnostics` présent dans A et B, MAC station égale à celle observée via le banc et identifiants
  de builds distincts et attendus.
- Jeton de maintenance et identité TLS compatibles entre A et B.
- Image B et manifeste IAM1 privés, approuvés et SHA-256 vérifiés.
- Sauvegarde *post-staging*, correspondant octet pour octet à toute la flash,
  avec procédure de restauration documentée.
- Liste explicite des régions qui doivent rester bit-à-bit identiques.
- Consentement spécifique à l'activation, au reboot et à la réécriture de
  `otadata` / `ota_meta` par le moteur OTA.

La présence d'une sauvegarde et d'un plan ne prouve pas que la restauration
est réellement utilisable; vérifier préalablement le chemin ROM adapté à la C3.
Aucun geste électrique pendant l'écriture n'est autorisé par cette recette.

## Plan privé

Cet exemple de schéma doit être remplacé par les observations réelles.
Les offsets ci-dessous illustrent le profil 4 Mio; ne pas les supposer exacts :

```json
{
  "schema": 1,
  "scope": "ota.activate-confirm-readback",
  "device": "esp32-local",
  "mcu": "esp32c3",
  "flash_size": 4194304,
  "table_offset": 32768,
  "pre_activation_flash": "/private/ota/flash-after-stage.bin",
  "pre_activation_sha256": "<sha256 hex>",
  "baseline_build_id": "qualification-A-001",
  "candidate_build_id": "qualification-B-001",
  "candidate_image": "/private/ota/B/app.bin",
  "candidate_sha256": "<sha256 hex>",
  "candidate_manifest": "/private/ota/B/app.manifest",
  "deployment_id": "qualification-B-001",
  "otadata_offset": 53248,
  "ota_meta_offset": 61440,
  "slot_0": {"offset": 131072, "size": 1572864},
  "slot_1": {"offset": 1703936, "size": 1572864},
  "preserved_regions": [
    {"label": "config", "offset": 3932160, "size": 262144}
  ]
}
```

Les chemins de sauvegardes/manifestes et les secrets restent hors Git.
`OTA_ACTIVATION_PLAN_SHA256` désigne le SHA-256 du plan JSON exact.

## Exécution après approbation spécifique

```sh
umask 077
# Environnement privé : BENCH_URL, BENCH_DEVICE, BENCH_CLIENT_TOKEN
# OTA_HTTPS_ORIGIN, OTA_CA_FILE, IOBEWI_OTA_TOKEN
export OTA_ACTIVATION_PLAN=/private/ota/activate-plan.json
export OTA_ACTIVATION_PLAN_SHA256=SHA256_OF_ACTIVATION_PLAN
export OTA_APPROVED_ACTIVATION=yes
python -m pytest tests/ota_bench/test_activation.py --bench \
  --bench-results /private/ota/evidence/activate \
  --junitxml=/private/ota/evidence/activate.xml -v
```

Le test compare le SHA-256 de toute la flash avant activation avec le snapshot
approuvé, vérifie la présence et le digest de l'image B dans le slot inactif,
observe le build A, puis libère la première réservation avant le POST.
Il n'envoie **qu'un seul** `/ota/activate`, jamais rejoué automatiquement.

Il attend ensuite l'identité de B par HTTPS. Après sa confirmation, il
acquiert une nouvelle réservation liée à la génération courante, relit
`otadata`, vérifie le passage durable à `Valid` et la conservation du
fallback confirmé A. Il relit séparément les deux copies OTSF de `ota_meta`,
exige que l'état de staging soit `None` et que l'identité/digest du déploiement
confirmé ait été promue. Les régions préservées sont également comparées au
snapshot antérieur.

Si l'opération entraîne un changement d'epoch, une rupture de preuve ou
une quarantaine, la campagne échoue et exige un diagnostic opérateur,
sans reprise forcée.

Pour B → A, préparer une **nouvelle image A candidate**, un nouveau
staging, un nouveau snapshot et un nouveau plan d'activation distinct.
Il ne faut pas assimiler une ancienne image A restée en flash à une candidate
nouvellement autorisée, ni effacer le fallback confirmé.

## Limites de preuve

- Le diagnostic vérifie la correspondance entre l'identité du binaire en
  cours et l'entrée BOOT v2 `Valid`, mais **n'authentifie pas** la signature.
- Les relectures indépendantes `otadata` et `ota_meta` fournissent les deux
  observations durables BOOT v2 et OTSF/OTM1, avec contrôle CRC et ordre de
  génération. Ces CRC ne constituent pas une authentification cryptographique.
- L'association HTTPS ↔ port physique exige la comparaison exacte des MAC
  station observées par le firmware et par `identify` au travers du banc.
  Cette correspondance est une identité matérielle de qualification, pas une
  racine de confiance cryptographique contre un firmware compromis.
- Ni un PASS hôte ni le succès du build C3 ne constituent une campagne
  matérielle. Les scénarios de coupure, hang-self-check et corruption
  nécessitent des recettes et autorisations dédiées.

## Statut

| Élément | Verdict |
| --- | --- |
| Build C3 avec diagnostic, CI #41873220567 | PASS |
| Tests offline initialement intégrés, même CI | PASS |
| Staging sur C3 | NON EXÉCUTÉ |
| Activation, confirmation, alternance A/B | NON EXÉCUTÉ |
| Rollback/coupures | NON EXÉCUTÉ |
