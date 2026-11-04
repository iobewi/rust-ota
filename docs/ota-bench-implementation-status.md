# Développement des recettes OTA avec le banc — état de la branche

Référence: rust-ota `main` à `20d8a6601664b746c914fc887c67d712efe50b2a`.
Le client du banc provient de rust_dev PR #4, SHA `54c69ecc2bbbbd95d682301a8017e18ccb371a51`.

## Fichiers

- `tests/ota_bench/conftest.py` : fixture de qualification intégrant `Campaign` (précontrôle, provenance, cleanup).
- `tests/ota_bench/test_preflight.py` : identification MCU et lecture conditionnelle de la table de partitions.
- `tests/ota_bench/ota_http.py` : adaptateur applicatif HTTPS minimal à usage de recette. Aucun accès série, aucun retry, erreurs de transport indéterminées distinctes d'un refus HTTP.
- `tests/ota_bench/test_http_contract.py` : tests hôte des entêtes et identifiants/protocoles.
- `tests/ota_bench/test_http_transport.py` : transport adversarial sans retry et bornage des réponses.
- `tests/ota_bench/boot_metadata.py` et `test_boot_metadata.py` : décodeur BOOT v2 avec vecteurs indépendants, contrôles CRC/commit et injections de corruption.
- `tests/ota_bench/ota_meta.py` et `test_ota_meta.py` : décodage indépendant OTSF/OTM1 (deux copies, CRC, séquence, état transactionnel) et corruption/coupure simulée.
- `tests/ota_bench/test_staged_image.py` : staging sous accord précis, preuve par relecture de l'image et OTM1 `Written`.
- `tests/ota_bench/test_activation.py` : activation sous accord distinct et observation BOOT v2 + OTM1 finalisé et régions préservées.
- `tests/ota_bench/boot_transitions.py` et `test_boot_transitions.py` : assertions hôte A→B→A, conservation du repli Valid, absence de probation résiduelle et rejet Aborted/Invalid.
- `tests/ota_bench/test_boot_snapshot.py` : lecture de `otadata` via le banc avec offset explicite, vérification du format et collecte privée SHA-256.
- `tests/ota_bench/test_upload_preparation.py` : tests hôte de la vérification locale des images/manifests, avant transport.
- `tests/ota_bench/test_http_readonly.py` : GET /health et refus syntaxique d'activation. Ce dernier exige `OTA_ENABLE_SAFE_NEGATIVES=yes` car il émet un POST applicatif.

## Exécution

Installer le paquet `bench/python[pytest]` depuis le SHA exact de la PR #4. Avec la branche de rust-ota cochée :

```sh
# Tests locaux sans --bench, sans connexion physique :
python -m pytest tests/ota_bench/test_http_contract.py tests/ota_bench/test_http_transport.py tests/ota_bench/test_upload_preparation.py tests/ota_bench/test_boot_metadata.py tests/ota_bench/test_boot_transitions.py -q

# Collecte et skip des tests matériels (incluant précontrôle) :
python -m pytest tests/ota_bench -q
```

Les imports `ota_http` sont volontairement locaux au dossier pytest. Les rapports et dumps doivent être conservés hors Git. **Ce document décrit des recettes créées, pas un résultat d'exécution.**

Pour le banc réel, l'exemple `bench/docs/pytest.md` reste la référence. Définir `BENCH_URL`, `BENCH_DEVICE` et `BENCH_CLIENT_TOKEN` de manière privée, et lancer sélectivement les tests avec `--bench`. La lecture de partitions exige une adresse explicitement vérifiée via `OTA_PARTITION_TABLE_OFFSET`. Aucun flash write n'existe encore dans cette première tranche.

Pour un contrôle HTTPS en lecture seule, renseigner `OTA_HTTPS_ORIGIN`, `OTA_CA_FILE`, `IOBEWI_OTA_TOKEN` et lancer uniquement `-k health_is_reachable`. Le firmware de référence ne publie qu'un corps `ok` : cela **ne prouve ni l'identité de l'image ni l'état OTA**.

## Couverture réelle

| Cas | Présence d'une recette | Preuve sur carte |
| --- | --- | --- |
| Identification API et état préliminaire | oui, nécessitant --bench | NON EXÉCUTÉ |
| Partitions | oui, avec offset explicite | NON EXÉCUTÉ |
| Contrat HTTP local | oui, tests hôte | NON EXÉCUTÉ |
| Hash candidat/manifeste local | oui, tests hôte | NON EXÉCUTÉ |
| /health TLS | oui, sans identité OTA | NON EXÉCUTÉ |
| BOOT v2: format et corruption | oui, tests hôte + capture flash opt-in | NON EXÉCUTÉ |
| BOOT v2: transitions nominales/rollback | assertions hôte sur snapshots, sans identité runtime | NON EXÉCUTÉ |
| Refus d'ID invalide | oui, POST explicitement opt-in | NON EXÉCUTÉ |
| Upload signé et publication durable | oui, staging gardé et relecture OTSF/OTM1 | NON EXÉCUTÉ |
| Activation / probation / confirmation | oui, chemin nominal gardé et relecture durable | NON EXÉCUTÉ |
| Alternance A-B-A | non | NON EXÉCUTÉ |
| Refus post-écriture / interruption | non | NON EXÉCUTÉ |
| Rollback et coupure | non | NON EXÉCUTÉ |

## Préconditions au prochain chantier

Ne pas ajouter de tests OTA destructifs prétendant qualifier la publication ou le rollback sans :

1. observation durable de l'identité, du slot et des états OTM1/boot ;
2. géométrie de la C3 réellement identifiée et validée ;
3. sauvegarde de la flash complète et plan de restauration cohérent avec le transport réel ;
4. images A/B et enveloppes produites et hashées ;
5. liste de plages à modifier et approbation de l'opérateur avant toute écriture ;
6. périmètre distinct approuvé pour les coupures pendant programmation.

L'adaptateur HTTPS envoie désormais des blocs de 2048 octets. Il vérifie le SHA-256 du fichier avant l'envoi et requiert `expected_sha256` et `max_bytes` issus de la préparation autorisée. Il re-hashe les octets émis. Tout transport indéterminé reste une erreur fatale sans retry. Le résultat HTTP `200 staged` est une publication déclarée, pas une preuve d'exécution ou de confirmation.

Le décodeur BOOT v2 n'est pas un interprète OTM1, n'authentifie pas l'image et n'observe pas le slot réellement exécuté. Ses rapports doivent donc afficher ces trois limites.

**Validation** : fichiers publiés sur la branche, mais non exécutés depuis cette session (accès GitHub indisponible depuis l'environnement Python local). Ne pas annoncer PASS, même pour les tests hôte, avant exécution/CI exacte.
