# Chronologie et portée des preuves

Cette campagne suit l'audit indépendant Astra du 13 novembre 2026 et le choix
explicite de privilégier les extraits exacts. Les rapports de prose antérieurs
dans `reports/` restent historiques. Aucun résultat n'est réécrit en succès.

- `initial-*` : défauts de la version initialement examinée ; certains résultats
  utilisent volontairement un critique optimiste simulé, sans appel fournisseur.
- `section-fix-intermediate.json` : état intermédiaire après correction des alias
  de dosage, avant la frontière extractive. Ses publications de fausses phrases
  ne décrivent donc pas le résultat final.
- `context-reassembly-*` : preuve du contexte complet et des 556 textes d'index
  inchangés. Aucun fichier du corpus n'est réécrit.
- `adversarial-replay.json` : nouveau replay avec verdict `entailed` explicitement
  injecté. Mesure la non-publication de phrases falsifiées, pas une fréquence
  réelle d'attaque ni une garantie de pertinence de toute preuve choisie.
- `browser-*.json` : état UI, réponses de génération interceptées ; ce ne sont pas
  des validations médicales ni des réponses réelles du fournisseur.
- `http-acceptance.json` : campagne séquentielle de vrais appels `/ask`, avec
  provenance, critères publics renforcés, téléchargements des sources, durée et
  empreintes des fichiers. Les cas généraux sans barème factuel indépendant
  établissent surtout structure, sources et statut attendu.
- `validation.json` : synthèse mesurée de cette version.
- `http-focus-final.json` : réponses de la version avec focus littéraux, score brut
  14/15 immuable. `http-focus-regraded.json` conserve chaque ancien score et le
  recalcul 15/15 après correction de la notation eGFR), sans nouvel appel.
- `astra-before-focus-review.md` et `astra-focus-final-review.md` : deux états
  distincts ; la dernière revue couvre les quinze réponses et les seize citations.
- `focus-relevance-limit.json` : un critique optimiste peut encore approuver un
  contexte exact mais hors sujet. Le barème le rejette ; cette injection n'est pas
  une erreur observée du fournisseur réel.

Le nouveau barème est décrit dans `eval/README.md`. Les scénarios additionnels
ont été fixés avant les nouveaux appels réels ; ce n'est pas un jeu aveugle externe.
Tout retest est enregistré séparément et ne transforme pas la série complète.

La revue de pertinence et de complétude reste faillible, même quand le texte est
strictement littéral. Le projet est une démonstration locale, sans validation
clinique. Aucun dépôt public ou envoi de remise n'est attesté par ces fichiers.

## Archive livrable

`package-smoke.json` et `package-tests.xml` attestent 271 tests réussis après
extraction du ZIP dans un dossier neuf sans `.env`, avec import de l’application
depuis cette extraction. Les dépendances sont celles de l’environnement verrouillé
existant ; ce contrôle ne prétend pas réaliser une installation à froid. Le paquet
final inclut ces preuves et conserve les empreintes du code testé.

`pdf-verification.json` consigne les 26 pages et leur vérification visuelle.
