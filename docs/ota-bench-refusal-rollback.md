# Recettes de refus et vérification de rollback — qualification OTA

## État

Ces contrôles sont ajoutés à la branche de préparation. Leur présence dans le
dépôt ou un PASS sur fixtures hôte **ne signifie pas** qu'une C3 a subi un
rollback réel.

Aucune injection de panne, coupure, écriture flash ni effacement n'est déclenché
par ces nouvelles recettes.

- `test_refusal_assertions.py` : tests hôte des statuts/corps HTTP exacts et de
  la conservation octet pour octet de `otadata` et `ota_meta`.
- `test_diagnostic_security.py` : GET de diagnostic sans jeton, attendu 401.
  La recette vérifie aussi le diagnostic authentifié avant/après et la liaison
  de MAC station avec l'identité du banc. **Pas de preuve OTM1** dans ce test.
- `rollback_proof.py` : contrôles de métadonnées BOOT v2 et OTSF/OTM1 pour
  un candidat rejeté, avec fallback toujours confirmé et identité active
  inchangée. L'état de staging après rejet n'est pas supposé.
- `test_rollback_capture.py` : analyse exclusivement hors matériel de preuves
  enregistrées. Elle demande également le diagnostic du firmware exécuté après
  retour au fallback : des métadonnées seules ne prouvent pas son exécution.
- `test_rollback_proof.py` et `test_rollback_capture_contract.py` :
  tests hôte des chemins valides et de plusieurs faux positifs.

## Lancer sans accès matériel

```sh
python -m pytest \
  tests/ota_bench/test_refusal_assertions.py \
  tests/ota_bench/test_rollback_proof.py \
  tests/ota_bench/test_rollback_capture_contract.py -q
```

Pour un contrôle **lecture seule** sur la carte, après avoir vérifié la connexion
et les préconditions du banc :

```sh
# BENCH_URL, BENCH_DEVICE, BENCH_CLIENT_TOKEN et OTA_HTTPS_ORIGIN,
# OTA_CA_FILE, IOBEWI_OTA_TOKEN, OTA_EXPECTED_BUILD_ID,
# OTA_EXPECTED_CHIP restent définis dans un environnement privé.
python -m pytest tests/ota_bench/test_diagnostic_security.py --bench \
  --bench-results /private/ota/evidence/diag-401 \
  --junitxml=/private/ota/evidence/diag-401.xml -v
```

Le transport du banc peut entraîner un reset pendant `identify()`. Ne pas
déduire de ce test une absence absolue d'écriture interne ou une protection de
l'application contre un firmware compromis.

## Analyse de preuves de rollback déjà collectées

L'analyse s'effectue depuis un manifeste privé, sans connexion au banc et sans
réécriture. Elle demande cinq fichiers : deux états BOOT, deux états OTM1 et un
diagnostic JSON récupéré sur le firmware après rollback.

Structure du manifeste (schéma de **preuve**, non langage d'exécution) :

```json
{
  "schema": 1,
  "scope": "ota.rollback-forensic",
  "mcu": "esp32c3",
  "fallback_slot": 0,
  "fallback_build_id": "qualification-A-001",
  "station_mac": "aa:bb:cc:dd:ee:ff",
  "files": {
    "before_otadata": {"path": "/private/ota/boot-before.bin", "sha256": "<sha256>"},
    "after_otadata": {"path": "/private/ota/boot-after.bin", "sha256": "<sha256>"},
    "before_ota_meta": {"path": "/private/ota/meta-before.bin", "sha256": "<sha256>"},
    "after_ota_meta": {"path": "/private/ota/meta-after.bin", "sha256": "<sha256>"},
    "final_diagnostic": {"path": "/private/ota/diag-after.json", "sha256": "<sha256>"}
  }
}
```

Les champs d'identité et les chemins d'exemple **ne sont pas des observations
matérielles**. Les fichiers doivent être sauvegardés depuis les opérations
matérielles identifiées, avec SHA-256, epoch/génération et logs de provenance.
Les dumps binaires et leur manifeste restent hors Git.

```sh
export OTA_ROLLBACK_EVIDENCE_MANIFEST=/private/ota/rollback.json
python -m pytest tests/ota_bench/test_rollback_capture.py -q \
  --junitxml=/private/ota/evidence/rollback-forensic.xml
```

Sans manifeste, ce test est SKIP et n'annonce aucun résultat.

Le PASS de ce test démontre uniquement que les captures **fournies** et hashées
sont cohérentes avec les invariants connus : BOOT v2 candidat rejeté
(`Invalid` ou `Aborted`), fallback `Valid`, identité active OTM1 inchangée
et diagnostic du firmware de repli. La fiabilité des captures dépend de leur
provenance, le CRC n'est pas une authentification et aucune preuve de signature
ou d'anti-rollback matériel n'en résulte.

## Critère avant un vrai scénario de rollback

Il reste à produire et approuver séparément les firmwares de défaut
`reject-self-check` et `hang-self-check` et à démontrer qu'ils peuvent être
testés sans détruire l'unique fallback confirmé. Leurs premières écritures
nécessitent un plan exact, un backup et une autorisation. Une coupure physique
pendant écriture nécessite son propre consentement.
