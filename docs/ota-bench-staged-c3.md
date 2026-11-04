# Recette OTA C3 : staging contrôlé puis relecture indépendante

## État et limites

Cette recette est **écrite mais non qualifiée sur matériel**. L'existence du code n'autorise aucune écriture.
`tests/ota_bench/test_staged_image.py` n'est exécutée que lorsque toutes ses conditions sont réunies.
Elle **ne lance aucune activation**, ne provoque aucune coupure, ne modifie pas de grant et ne lève pas de quarantaine.

Le firmware doit être préparé avec `--features esp32c3,qualification-diagnostics`
et la variable de build publique `IOBEWI_OTA_QUALIFICATION_ID` (identifiant distinct A/B).
Une compilation avec ce diagnostic n'implique pas une preuve d'authenticité.
`/ota/diagnostic` nécessite le Bearer de maintenance et fournit
`build_id`, `mcu`, `running_slot`, les deux états `BOOT` v2;
`otm1_observed=false` et `image_authenticated=false` restent explicites.
La route n'existe pas sans la feature de qualification.

Le client OTA HTTPS est distinct de l'API REST du banc. Il ne prend pas le port USB.
Les erreurs de transport de POST sont indéterminées, jamais automatiquement rejouées.

## Préparer les images hors matériel

Le script existant `examples/ota-system/prepare.py --chip esp32c3 --auth signed`
est le point de départ; utiliser le générateur officiel de partitions ESP-IDF,
les clés de **test** hors Git, et les features et certificats exigés par la
composition. Lancer deux builds distincts avec des identifiants de qualification
différents, sauvegarder séparément les artefacts produits et leurs SHA-256.
Le script peut réutiliser son répertoire de sortie : copier l'image A et le
bootloader correspondant dans le stockage privé avant de lancer B.

Générer un manifeste IAM1 pour chaque image à l'aide de `ota_sign` et signer
avec la clé de test correspondant à la politique épinglée dans les firmwares.
Les deux images doivent conserver une configuration de connectivité compatible
ou le diagnostic HTTPS après activation deviendra indisponible.

Avant toute écriture, lire la capacité/RDID, la table réelle, les partitions et
les régions privées. La géométrie de `examples/ota-system/partitions.csv` ne
remplace jamais une découverte réelle.

## Plan privé explicite

Exemple **de structure uniquement**, non prêt à l'emploi.
Les valeurs ci-dessous sont des exemples de profil, pas des mesures matérielles :

```json
{
  "schema": 1,
  "scope": "ota.stage-and-readback",
  "device": "esp32-local",
  "mcu": "esp32c3",
  "flash_size": 4194304,
  "table_offset": 32768,
  "backup_file": "/private/ota/flash-before.bin",
  "backup_sha256": "<64 hexadecimal characters>",
  "image_file": "/private/ota/B/app.bin",
  "image_sha256": "<64 hexadecimal characters>",
  "manifest_file": "/private/ota/B/app.manifest",
  "deployment_id": "qualification-B-001",
  "baseline_build_id": "qualification-A-001",
  "ota_meta_offset": 61440,
  "slot_0": {"offset": 131072, "size": 1572864},
  "slot_1": {"offset": 1703936, "size": 1572864}
}
```

Conserver le plan et ses empreintes dans un dossier privé. L'adresse et les
dimensions de chaque slot doivent correspondre à la table réellement lue sur
la carte, indépendamment du CSV de build. Une sauvegarde existante doit être
vérifiée en totalité, y compris ses secrets privés, sans être placée dans Git.

Au moment de l'exécution, la recette relit l'intégralité de la flash et exige
une égalité SHA-256 avec la sauvegarde du plan **avant toute écriture**.
Un désaccord interdit l'upload.

## Lancement (uniquement après approbation de la première écriture)

1. Présenter la cible identifiée, la carte des partitions, le plan exact, les
   hashes A/B, la sauvegarde, l'accès ROM et la restauration à l'opérateur.
2. Obtenir son accord explicite sur ce périmètre de programmation OTA réseau.
3. Après accord, placer plan et secrets hors Git, puis renseigner les variables
   dans un environnement privé; ne pas mettre les tokens dans les arguments.
4. Lancer uniquement le test ciblé, séquentiellement, sans xdist.

```sh
umask 077
export BENCH_URL=http://127.0.0.1:8080
export BENCH_DEVICE=esp32-local
# BENCH_CLIENT_TOKEN : secret privé
# OTA_HTTPS_ORIGIN : adresse HTTPS du firmware
# OTA_CA_FILE : certificat CA approuvé
# IOBEWI_OTA_TOKEN : secret privé
export OTA_APPROVAL_FILE=/private/ota/stage-plan.json
export OTA_APPROVAL_SHA256=SHA256_OF_STAGE_PLAN
export OTA_APPROVED_STAGE=yes
python -m pytest tests/ota_bench/test_staged_image.py --bench \
  --bench-results /private/ota/evidence/stage \
  --junitxml=/private/ota/evidence/stage.xml -v
```

La recette enregistre les diagnostics séparément des secrets. Le POST HTTPS
n'est jamais rejoué, même si l'accusé de réception est perdu.

Un `200 staged` + relecture indépendante des octets de B et décodage de la
trame OTSF/OTM1 `Written` (SHA-256, slot et deployment ID) apportent une
preuve de publication durable observée. Ce verdict **ne prouve ni
l'activation de B, ni sa confirmation**, ni l'authenticité matérielle de la
signature ou du boot. Ces vérifications ont des tests distincts.

Le retour console après les lectures flash peut entraîner un redémarrage :
ne pas confondre cette observation avec un succès de boot OTA.

## Statut

| Scénario | Statut |
| --- | --- |
| CI C3 firmware diagnostics | PASS (run 41873220567, commit 842b4cb) |
| CI tests hôte initiaux | PASS (même run / commit) |
| Staging C3 via API | NON EXÉCUTÉ |
| Relecture indépendante C3 | NON EXÉCUTÉ |
| Activation, confirmation, rollback | NON EXÉCUTÉ |
