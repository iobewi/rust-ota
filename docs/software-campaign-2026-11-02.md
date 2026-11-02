# Campagne rust-ota sans matériel — 2 novembre 2026

Point de départ : main `fab250662da2863c99a78b1d6de8e9e4549f5fd4`, PR #10 fusionnée,
CI [41475570372](https://github.com/iobewi/rust-ota/actions/runs/41475570372) verte.
Les neuf issues #1–#9 étaient ouvertes. #14 est apparue pendant la campagne. Aucun correctif déjà intégré n'a été refait.

Aucun équipement, flash, reset, eFuse ou clé de production utilisé/modifié.
Aucune PR fusionnée, aucune issue clôturée. Les éléments ci-dessous sont proposés
par des PR séparées ; ils ne sont pas encore sur main. Qualification S3 acquise
conservée : tag `verified-boot-s3-qualified`, rust-mcu-libs #101/#105 et
`verified-boot-evidence.md`. Aucun nouveau PASS matériel ajouté à cette matrice.

## État des trois lots de la feuille de route

| Lot | Implémenté sur main avant campagne | Évidence / limite | Avancement proposé |
|---|---|---|---|
| 1 — Authentification des images | IAM1, profils unsigned/signed, clé/algorithme/cible/version, contrôle avant publication/activation ; RSA-PSS et P-256 selon profil | Tests hôte cryptographiques ; builds C3/S3 ; ne pas confondre digest et authenticité | #11 durcit publication/Activating ; #12 améliore précontrôles/diagnostic de repli |
| 2 — VerifiedBoot logiciel | IAP1, vérification des images et repli au boot, géométrie wide S3 | Profil **logiciel S3 qualifié** ; C3 seulement compilé ; pas de racine matérielle | #20 audit/protocoles ; #21 étude SBV2 ; #22 étude RP2350/RT1062 |
| 3 — Sécurité complémentaire/résilience | TrustPolicy à clés actives/révoquées et plancher statique ; mécanismes transactionnels et modèles de coupures | Pas de compteur protégé intégré ni de garantie générale après coupure ; rust-mcu-libs#70 reste ouvert | #13 panic ; #18 politique portable de promotion ; #19 comparaison du jeton ; #15/#16/#17 suivent intégration/persistance/clés/maintenance |

## Rapport par issue

Toutes les décisions de fusion supposent revue et CI verte sur la **tête exacte**.
Les liens de CI ci-dessous identifient les exécutions de ces têtes ; leur résultat
courant dans GitHub est l'autorité, jamais le succès d'une tête antérieure.

| Issue / état initial | Travail réalisé / PR | Tests et critères logiciels satisfaits | Matériel restant et risques résiduels | Décision proposée |
|---|---|---|---|---|
| #9 ouverte : publish écrase Activating | #11 : Conflict typé dans publish et propagation UploadManager ; begin/publish regardent l'état persistant même si digest non projetable | Profils signé/non signé, begin/publish entrelacés, activation suspendue, métadonnées corrompues, Activating à digest invalide ; octets identiques et zéro commit ; formats conservés | Aucun matériel requis. MetadataStore n'est pas un CAS : les appelants doivent sérialiser les workflows | Prête après CI/revue ; clôturable après fusion autorisée |
| #4 ouverte : preuve effacée avant upload, diagnostic agrégé | #12 : prélecture en-tête (magic/chip/count/hash requis) avant invalidation/supersession ; diagnostics digest/structure/canonical ; journaux de repli et procédure récupération | Tests des précontrôles, raisons distinctes, corruption et chaque préfixe d'image incomplet ; aucun changement IAP1/OTM1 | Qualification applicative refus/interruption/relecture indépendante restante. Deux slots ne préservent pas l'ancien slot après écrasement. Journaux par opération, pas télémétrie durable du repli | Correctif logiciel à revoir/fusionner ; issue maintenue ouverte pour critères restants |
| #3 ouverte : panic Stable fige | #13 : réarmer TIMG0 avant diagnostic, reset borné, aucune écriture de confirmation | Test du vrai planificateur BOOT : reset Stable réessaie, PendingVerify replie ; protocole panic/console bloquée | Expiration TIMG0 réelle, panic Stable/PendingVerify/console bloquée ; boucle de panics persistante possible | Correctif à revoir/fusionner ; issue ouverte jusqu'à qualification |
| #8 ouverte : grand lot sécurité | #18 : politique no_std et FloorStore ; contrats/identités/versions/clés/récupération/matrice ; #19 comparaison jeton ; enfants #15/#16/#17 | Promotions différées en probation, identité concordante, monotonie/idempotence, conflits et coupures avant/après commit simulées ; comparaison exhaustive des octets du jeton | Aucun anti-rollback intégré. Backend protégé, fenêtre confirmation→promotion, autorité/provenance durable, rotation/révocation, timer supervisé et coupures réelles restent à traiter | Briques testées à revoir ; parent et enfants ouverts |
| #1 ouverte : C3 non qualifié | #20 : audit ABI/ROM/adresses/features/flash/RAM, sources officielles et protocole C3 | Réutilisation des assertions de layout, modèles SHA/NIST/canaris et CI C3 ; pas de défaut statique démontré imposant un changement partagé | ROM RSA/SHA jamais exécutée sur C3 par cette campagne, pile/watchdog/boot/OTA/repli à qualifier ; aucun résultat S3 transféré | Maintenir ouverte |
| #2 ouverte : racine S3 absente | #21 : étude taille/geometrie/ROM, chaîne custom IAP1, autorités de clés, eFuses/chiffrement/récupération | Écart historique clarifié à partir de flash-geometry.md déjà intégré ; calcul signature/padding et architecture écrits | Packaging SBV2 et racine matérielle non implémentés ; provisioning/encryption/debug/replay/ROM staging à valider séparément | Étude à revoir/fusionner ; issue ouverte |
| #5 ouverte : deltas matériels absents | #20 : inventaire et protocoles par chemin ; #12 renforce préfixes tronqués ; #13 politique panic | Modèles NOR/BOOT/IAP1/auth déjà présents réutilisés ; protocole exige relectures/restauration exactes | Watchdog réel, rejet, HALT, repli inverse, ECDSA et coupures physiques non exécutés | Maintenir ouverte |
| #6 ouverte : aucune étude | #22 : RP2350A/B Arm et périmètre proposé Teensy4.0/4.1 RT1062 ; formats/crypto/OTP/budget/adaptateurs | Sources constructeur, distinction P-256/secp256k1/HAB, limites de format et méthode de dimensionnement, conditions de qualification | Aucun adaptateur, build ou qualification ; carte finale à choisir ; standard/Lockable et autres Teensy non équivalents | Étude prête à revue ; clôturable après acceptation/fusion, sans annoncer de support MCU |
| #7 ouverte : feuille de route périmée | Rapport présent et corps de #7 actualisés, toutes PR et issues filles reliées | Distinctions implémenté / testé hôte / compilé MCU / qualifié matériel conservées | Lots 2 matériel/multi-MCU et 3 intégration incomplets ; travail encore en PR | Maintenir ouverte |
| #14 créée pendant campagne : réorganisation firmware/ | Périmètre lu : déplacement seul, contenu Rust inchangé, 18 membres, chemins/packaging/preuves à vérifier | Aucun déplacement effectué ; ne fait pas partie des lots A–D initiaux. Revue d'impact : touche les chemins de toutes les PR en cours | Aucun matériel requis ; risque de conflits/chemins actifs périmés si traité avant intégration. Les nouvelles docs devront aussi être déplacées | Maintenir ouverte ; PR de réorganisation seule recommandée après intégration des présentes PR |
| #15 créée : plancher de sécurité | #18 fournit politique et contrat de persistance | Modèle déterministe, refus identité, version, monotonicité et reprise | Intégration boot/confirmation et backend protégé, récupération intention/promotion et tests matériels absents | Maintenir ouverte |
| #16 créée : clés/compromission | Contrats et scénarios dans #18 | Réutilise TrustPolicy et tests de révocation existants ; ne recrée pas le keyring | Autorité protégée et persistance de politique dynamique, anti-rejeu, récupération après compromission non intégrés | Maintenir ouverte |
| #17 créée : maintenance/résilience | #19 + matrice de #18 | Primitive sans allocation ; absence/secret vide/prefixes/extensions/toutes substitutions d'octet refusés ; handler système raccordé | Provisioning/TLS/resource limits, timer supervisé et persistance/coupures restent ouverts ; pas de qualification temporelle globale | Maintenir ouverte |

## Commits et CI distantes

Chaque CI standard couvre Host (tests, rustfmt, Clippy strict, outils), RISC-V C3,
Xtensa S3 **pinned**, puis gate fail-closed. Les scripts exécutent aussi les features,
profils signés/non signés, variantes SHA et contrôles de taille/géométrie prévus.
Le workflow est inchangé. Xtensa latest est prévu hors PR par la CI existante ;
le run main initial est vert. Aucun succès de build n'est une qualification MCU.

| PR | Tête exacte | Exécution CI |
|---|---|---|
| #11 | `e66eb68f2c458d7649db784899e95f3b12d834b6` | [41482643916](https://github.com/iobewi/rust-ota/actions/runs/41482643916) |
| #12 | `3a9a2513036c16be96d5819177f2538ddbc170a8` | [41480899537](https://github.com/iobewi/rust-ota/actions/runs/41480899537) |
| #13 | `7b08f3152865645fb1ff1cfb50c9b76af855771a` | [41482407892](https://github.com/iobewi/rust-ota/actions/runs/41482407892) |
| #18 | `36272b4fa4e189be1a9a3189a5c89fc255d22560` | [41480961690](https://github.com/iobewi/rust-ota/actions/runs/41480961690) |
| #19 | `55cae354d7074be0ea756b4b65b3c67d7e576e3c` | [41482421279](https://github.com/iobewi/rust-ota/actions/runs/41482421279) |
| #20 | `159a3a7aadbfa79f23d4a7375c1f87ff235c081e` | [41482752423](https://github.com/iobewi/rust-ota/actions/runs/41482752423) |
| #21 | `814e0704cf1f1f6e2a40f8e8e38afa058a32363a` | [41481733204](https://github.com/iobewi/rust-ota/actions/runs/41481733204) |
| #22 | `a750841bc306d35bb990e7596996cb0412ce31e6` | [41482123054](https://github.com/iobewi/rust-ota/actions/runs/41482123054) |

Validation locale : scripts ci_host.py complets pour chaque PR fonctionnelle,
dans des répertoires de build séparés ; tests ciblés après ajustements de composition.
Une composition temporaire locale des PR vérifie les interactions avant proposition
d'ordre de fusion. Cette composition n'est pas publiée/fusionnée dans main.
Les tests hôte ne prouvent ni l'ABI ROM réelle ni le comportement électrique de la NOR.

## Ordre recommandé, après accord explicite

1. #11 : priorité immédiate, aucune dépendance aux autres corrections.
2. #12 : upload/repli, à relire avec le nouveau conflit #11.
3. #13 : politique panic, indépendante fonctionnellement ; dépendance de test écrite
   de façon compatible avec #12.
4. #18 puis #19 : mécanismes indépendants (plancher et jeton), aucune promesse de
   stockage protégé. Exports séparés pour une composition sans conflit.
5. #20 puis #21 puis #22 : études/protocoles ; #20 renvoie aux améliorations #12/#13,
   #21/#22 aux contrats de #18.
6. PR du présent rapport/feuille de route en dernier : reflète l'état proposé.

Après chaque fusion autorisée, relire la CI du nouvel ensemble sur main et la
mergeabilité de la PR suivante. Ne pas confondre ordre de revue et dépendance de
code. Clôtures alors possibles : #9 et #6 (étude seulement). Traiter ensuite #14 dans une PR de réorganisation seule sur la nouvelle base. Les autres issues
restent ouvertes avec leurs critères non satisfaits explicites.
