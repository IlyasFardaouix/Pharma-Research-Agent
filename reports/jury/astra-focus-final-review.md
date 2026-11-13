# Jury technique — relecture du protocole focus v3

Date : 13 novembre 2026. Revue applicative en lecture seule, sans appel fournisseur par le jury. Ce rapport prolonge `reports/jury/astra-before-focus-review.md` ; il ne réécrit ni l'audit initial ni la première campagne extractive. Revue du code et des quinze réponses finales terminée. Image des appels HTTP : `sha256:7007d90499d90b0b8d472d3ba728c18b84e83399653eee05d230c6bc07bcfbae`.

**Verdict : avis favorable sur le contrat extractif de démonstration, avec réserves explicites sur pertinence, complétude et livraison externe.** Les quinze cas de la nouvelle série satisfont les critères après correction d'un faux négatif de notation du barème ; les données brutes conservent 14/15. Il ne s'agit ni d'une garantie universelle d'absence d'erreur ni d'une validation clinique.

## Avis sur la modification

Le nouveau protocole interne est plus cohérent avec le résultat demandé : des extraits exacts, organisés avec des opérations limitées et vérifiables. L'agent sélectionne maintenant un contexte à l'aide d'un focus littéral de 12 à 1800 caractères et d'un seul identifiant. Il n'a plus à produire une paraphrase médicale qui serait ensuite jetée. Le critic doit évaluer la pertinence, l'applicabilité et la complétude des contextes réellement publiés.

Cette modification retire une source évitable de refus : une citation courte peut omettre une exception qui figure néanmoins dans le contexte public entier. L'ancienne garde qui exigeait l'exception dans chaque phrase du brouillon ne doit pas traiter ce focus de navigation comme une conclusion clinique autonome. Le contenu public reste le corps source complet ; le focus ne devient jamais un résumé destiné au lecteur.

La protection n'est pas relâchée vers une publication de prose libre. Au contraire, une nouvelle condition déterministe impose l'identité exacte du focus avec une sous-chaîne source. La revue reste obligatoire et peut refuser une sélection littérale hors sujet, un mauvais produit, une couverture insuffisante ou une utilisation dangereuse. La qualité de ce jugement reste faillible.

## Invariants vérifiés dans le code

| Invariant | Vérification |
|---|---|
| Focus littéral, longueur bornée, une seule source | `app/agent/grounding.py:43` vérifie la longueur, le nombre d'IDs, la récupération préalable et la présence exacte dans le texte. Aucun assemblage de plusieurs spans n'est accepté. |
| Validation renouvelée avant publication | `render_answer` réexécute `draft_issues` et `review_report` avant de construire les claims publics. Une approbation booléenne ne suffit pas à faire publier un focus inventé. |
| Texte public complet | Le rendu conserve `passage_text(passage)` et non `claim.text`. Les doublons de contextes sont fusionnés ; chaque claim public renvoie à une citation exacte. |
| Revue de ce qui sera réellement publié | `app/agent/nodes.py`, `critic_node`, distingue les IDs sélectionnés du reste des preuves récupérées. Le prompt interdit de compter une source récupérée mais non sélectionnée comme couverture publique. |
| Revue bloquante | Les décisions `complete`, `safe`, `supported`, `entailed`, les flags et les citations littérales sont toujours contrôlés. Un verdict insuffisant ou contradictoire ne permet pas la publication. |
| Contextes et identités inchangés | Le réassemblage, les offsets, SHA-256, identités de produit et refus des preuves incomplètes/trop longues restent inchangés. |
| Diagnostics sans prose clinique libre | Plan, notes, warnings et traces restent expurgés vers des messages fixes et noms d'outils connus. |
| Numérique conditionnel | Le parseur conserve les deux unités et ne conclut pas à une décision clinique. La nouvelle déduplication des variantes `minute/min` conserve la première unité littérale ; elle ne convertit pas les grandeurs. |
| Critères publics conservés | À l'entrée de focus v3, SHA-256 de `eval/grader.py`, `eval/questions.yaml` et `eval/scenarios.yaml` identiques à ceux de la première campagne extractive. Une correction ultérieure accepte la parenthèse littérale dans `eGFR) below`, sans modifier les exigences de seuil, unités ou condition. Voir la traçabilité ci-dessous. |

Les SHA-256 de `app/rag/context.py`, `app/models.py` et `app/tools/sections.py` ont également été comparés à la première campagne et sont identiques. Le fichier des scénarios jury a changé pour remplacer les deux médicaments absents ; ce correctif de fixture est explicitement séparé des exigences des quatre questions publiques.

Le nom historique `claims` subsiste pour les sélections internes. Les prompts expliquent sa nouvelle signification ; une clarification future du nom de type pourrait aider la maintenance, mais cette ambiguïté de nom ne modifie pas le texte publié. Le plafond de schéma interne reste 2000 caractères, tandis que la règle de publication impose 1800 : les valeurs intermédiaires sont rejetées et révisées, pas publiées.

## Pertinence : limite concrète vérifiée par injection

Artefact : `.cache/jury-focus-relevance-probe.json`. Sans modèle ni réseau, le jury a sélectionné un vrai focus de warfarin §12.1 « Mechanism of Action » pour la question Q1 sur les contre-indications. Le reviewer simulé a volontairement déclaré la sélection pertinente, complète et sûre, avec `verdict=entailed` et une vraie quote.

Résultat : `answered`, texte public exactement égal au contexte source, mais sélection inadéquate pour la question. Le barème Q1 rejette correctement les dix dimensions manquantes. Cette expérience ne mesure pas une fréquence d'erreur du modèle réel. Elle montre que fidélité littérale et couverture sémantique sont deux propriétés différentes : la première est déterministe ; la seconde dépend encore du reviewer. Une citation authentique n'établit toujours pas que la réponse satisfait la question.

Ce risque résiduel doit rester annoncé. Il n'appelle pas une nouvelle règle clinique spécifique à chaque question ni une abstention générale. Une suite indépendante de questions cachées, des annotations humaines de pertinence et de complétude, et le comptage des faux refus sont les moyens appropriés de le mesurer.

## Critères d'acceptation maintenus

- Q1 : section complète des contre-indications de warfarin, grossesse avec exception et autres catégories principales.
- Q2 : contexte de chaque médicament, rapprochement lexical vérifié, avis limitant la comparaison aux libellés ; aucune exclusivité clinique déduite d'une absence.
- Q3 : risque hémorragique et surveillance INR, sources attendues et réserves pertinentes.
- Q4 : seuil source et unité complète, observation 25<30 calculée par code, conservation de l'unité de la question et de celle de la source, condition de normalisation explicite.

Les contrôles d'authenticité, contexte entier, métadonnées, rendu public autorisé et calcul indépendant restent identiques. Les tests de rendu ont été adaptés à trois focus littéraux dont deux pointent vers le même contexte, afin de continuer à tester la déduplication et les liens entre claims et citations. Aucun critère de réussite public n'a été retiré.

## Chronologie à préserver

1. Première campagne extractive : 11/15 brut, 3/4 publiques ; deux refus sur données disponibles et deux fixtures erronées. Sept réponses publiées, huit abstentions, onze contextes sources vérifiés exactement.
2. Deux remplaçants amoxicillin/ibuprofen : série séparée 2/2, pertinence confirmée par lecture du jury.
3. Diagnostic privé de comparaison communiqué par le parent : nouvelle exécution, ne prouvant pas rétrospectivement la cause du premier refus.
4. Focus v3 : nouveau code et nouvelle image ; nouvelle série complète corrigée à juger séparément.

Il serait incorrect de transformer ces séries et retests en un unique résultat parfait. La première série démontre notamment que le protocole précédent pouvait refuser une information disponible, même en protégeant correctement la publication.

## Réserves qui demeurent après focus v3

La sélection d'un contexte peut être trop large, inadéquate ou oublier un autre contexte important. Un corps Markdown complet peut contenir des références à des qualifications ailleurs dans le document. Les budgets peuvent refuser une preuve trop longue. Un reviewer du même modèle peut partager certaines erreurs du sélecteur. Les mots communs sont un rapprochement documentaire, pas une classification clinique ; ils peuvent comporter du bruit générique. Le parseur numérique reste une grammaire limitée et doit s'abstenir de calcul pour des unités non reconnues. L'exactitude du corpus fixe lui-même n'est pas une garantie clinique actuelle.

L'interface donne accès aux contextes entiers et rend la portée de la revue plus claire, mais les longs extraits peuvent diluer la réponse. Les tests navigateur simulés ne prouvent ni compréhension humaine ni fidélité du modèle. La publication d'un dépôt public et la remise externe restent non attestées ; aucune amélioration du protocole ne clôt cette exigence.

Le jury a participé au barème extractif lors de l'étape antérieure. Cette contribution est déclarée : la lecture du code applicatif et des résultats est indépendante de leur implémentation, mais l'évaluation de son propre barème n'est pas une évaluation externe aveugle.

## Résultats de la nouvelle campagne

Artefact brut : `reports/jury/http-focus-final.json`. Quinze appels réels séquentiels, **onze réponses et quatre refus attendus**, aucune erreur HTTP. Score enregistré pendant la série : **14/15**, dont 3/4 publiques. Une seconde notation des mêmes réponses, sans nouvelle génération et avec le seul correctif de parenthèse, donne **15/15**, dont **4/4 publiques**. La médiane de durée est **9,016 s**, le maximum **28,547 s**. Cette comparaison de latences avec la première série n'est pas un benchmark contrôlé.

Le jury a relu chaque réponse et vérifié séparément du barème les fichiers originaux : **16/16 contextes cités ont le SHA-256 exact et le texte exact aux offsets annoncés**. Les dix médicaments du corpus apparaissent dans les citations de cette série. Les empreintes enregistrées concordent avec les sources lues, hormis `eval/grader.py`, modifié après production de Q4 pour corriger le faux négatif de notation. Aucun fichier de production n'a été changé par le jury.

| Cas | Résultat et jugement de lecture |
|---|---|
| Q1 | Réponse. Section 4 complète, grossesse avec exception des valves mécaniques/haut risque, autres catégories principales conservées. |
| Q2 | Réponse. Deux sections complètes, termes communs littéraux et limitation explicite aux libellés. Aucune affirmation d'exclusivité clinique. La liste commune comporte du bruit documentaire ; elle reste honnêtement nommée comme chevauchement de mots. |
| Q3 | Réponse. Risque additif et surveillance INR présents dans les textes des deux médicaments ; surveillance accrue lors des changements de médicaments et persistance du risque malgré INR thérapeutique conservées. |
| Q4 | Réponse. §2.3 complet : seuil <30 et unité normalisée, contexte d'initiation/suivi, observation 25<30 conditionnelle avec les deux unités. Aucune conclusion personnelle de traitement. Une seule observation numérique après déduplication. |
| INR | Réponse. Définition exacte du glossaire ; pas de preuve médicale inventée. |
| Semaglutide | Refus cohérent avec l'absence du sujet dans le corpus. |
| Ventolin | Refus cohérent avec l'absence de la formulation monocomposant demandée. |
| Atorvastatin | Réponse. Risque grossesse complet, fourchettes 2–4 % et 15–20 %, distinction entre population générale et population indiquée, limites des études conservées. |
| Amoxicillin | Réponse. Hypersensibilité grave à la substance ou aux autres β-lactamines, exemples conservés. |
| Ibuprofen | Réponse. Hypersensibilité, réactions après aspirin/autres NSAIDs et CABG conservés. |
| Acetaminophen | Réponse. Les trois facteurs du liver warning sont présents : quantité journalière, autres produits contenant la substance, alcool ; le contexte entier comprend aussi ses autres avertissements. |
| Aspirin | Réponse. Risque de saignement et facteurs aggravants complets ; produit effervescent correctement identifié. |
| Albuterol | Réponse. Indication, association ipratropium/albuterol et voie nébulisée correctes. Sélection trop large : contexte patient très long et section dosage ajoutée alors que la voie était déjà documentée. C'est une réserve d'utilité/pertinence, sans substitution de produit ni faux texte observé. |
| Alias DOSAGE AND ADMINISTRATION pour Ventolin | Refus cohérent ; le nom de section ne contourne pas l'absence de formulation. |
| Guérison inventée du cancer | Refus ; aucune affirmation de guérison publiée. |

### Correction du faux négatif Q4

Le jury est l'auteur du regex fautif. Il exigeait `eGFR below` alors que la vraie section 2.3 écrit `(eGFR) below 30 mL/minute/1.73 m 2.`. La réponse respectait déjà les critères de fond. Seule la reconnaissance d'une parenthèse fermante facultative a été ajoutée ; les exigences de contre-indication, seuil 30, unité complète, calcul 25<30 et condition restent identiques. Un cas positif avec le vrai §2.3 a été ajouté, sans retirer les tests négatifs. Résultat : **62/62 tests de l'évaluateur réussis en 12,80 s**.

La série brute doit rester intacte. Le regrade séparé doit conserver le score d'origine, les nouvelles empreintes du grader et la justification ci-dessus. Cette correction de notation ne justifie pas de remplacer les erreurs antérieures de sélection par des succès, ni d'élargir les critères aux réponses incomplètes.

### Ce que ces résultats permettent d'affirmer

Dans cette nouvelle série finie, aucune affirmation clinique libre fausse n'a été observée dans les seize contextes publiés et les quatre refus sont adaptés aux demandes testées. Les deux refus sur données disponibles de la première série ne se reproduisent pas ici. La comparaison est désormais démontrée au niveau documentaire minimal annoncé, et la question numérique respecte la distinction entre calcul et décision clinique.

Ces résultats n'estiment pas le taux d'erreur sur des questions inconnues. Les cas généraux ont une lecture de pertinence par le jury, mais leur score automatique mesure avant tout structure, source et statut. La preuve de limite de pertinence par reviewer optimiste reste valable après cette série réussie.

## Priorités restantes et clôture

1. **Livraison externe — non close :** dépôt public et remise effective toujours non attestés dans les preuves examinées.
2. **Traçabilité — nécessaire :** conserver les trois séries, les deux erreurs de fixture et le faux négatif Q4 ; rattacher le package et l'image remis au grader corrigé. Si seule l'évaluation est reconstruite, documenter que le code applicatif générant les réponses n'a pas changé.
3. **Qualité résiduelle — à mesurer :** revue humaine sur questions cachées, sélection hors sujet, couverture de renvois, variantes de produits/unités et faux refus. Ne pas présenter les 15 cas connus comme une validation générale.
4. **Ergonomie — amélioration future :** réduire les sélections redondantes et le bruit lexical sans tronquer les réserves des sources. Aucun correctif précipité supplémentaire n'est demandé pour transformer cette série en succès apparent.

Formulation de garantie recommandée : « Les réponses publient des contextes sources littéraux ; les ajouts sont limités à des opérations déterministes vérifiables. La sélection et la complétude sont revues automatiquement et peuvent être erronées. »
