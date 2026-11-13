# Relecture du jury — architecture extractive finale

Date : 13 novembre 2026. État du rapport : revue du code, vérifications hors réseau et lecture de la première campagne HTTP extractive terminées. Les diagnostics/retests ultérieurs sont distincts. Image de cette campagne : `sha256:03e028ad4732e001f287d9b2b544129b4e85c199670898d37faed239aeef6945`. Le sujet confidentiel a été consulté lors de l'audit initial et n'est pas reproduit ici.

## Verdict

Le changement répond de manière cohérente au choix explicite de l'utilisateur : « Extraits exacts en priorité, avec synthèse limitée aux éléments vérifiables ». Le contenu factuel public est désormais reconstruit à partir des contextes sources complets, avec une identité de produit, des citations et une portée de validation explicites. Les paraphrases du brouillon et les commentaires libres du critique ne sont plus le texte factuel publié. Cette modification supprime le mécanisme précis qui permettait auparavant à une fausse affirmation accompagnée d'une vraie citation d'être affichée comme réponse approuvée.

La planification, le choix d'outils, la recherche, le brouillon, la revue et les révisions sont conservés. Le projet n'est donc pas remplacé par une simple table de réponses ou une abstention systématique. Pour les questions composées, le résultat organise plusieurs preuves et ajoute seulement des rapprochements lexicaux et une observation arithmétique conditionnelle. Cette réponse composée minimale est défendable pour le sujet et conforme à la préférence utilisateur. Elle ne vaut toutefois pas une synthèse clinique, et un évaluateur exigeant une conclusion médicale reformulée pourrait juger sa portée insuffisante. Cette limite doit être annoncée, non dissimulée par le barème.

Le projet ne démontre ni « zéro hallucination » universel, ni pertinence parfaite, ni complétude de toutes les réponses. Il démontre des invariants de publication plus étroits, vérifiables et utiles. La remise publique Git reste une exigence externe non attestée dans cette revue. La qualification de l'image finale dépend encore des résultats de la campagne HTTP et des vérifications de livraison effectuées par le parent.

## Indépendance et preuves

Le jury a réalisé l'audit initial de façon indépendante et n'a modifié aucun fichier de production. Il a ensuite été explicitement chargé d'implémenter le nouveau barème dans `eval/grader.py`, sa documentation et `tests/test_eval.py`. Sa relecture des correctifs applicatifs demeure distincte de leur implémentation, mais la validation de son propre barème n'est pas une évaluation externe aveugle. Une seconde lecture humaine de ce barème est recommandée ; il ne faut pas présenter les tests qu'il a lui-même écrits comme une certification clinique indépendante.

Preuves directement obtenues par ce jury :

- État initial : 144 tests réussis en 92,86 s ; quatre injections hors réseau ont montré des fausses affirmations publiées avec citations authentiques, dont trois réussissaient l'ancien barème. Ces injections simulaient un reviewer défaillant ; elles ne mesuraient pas le taux d'erreur du modèle réel.
- Erreur réelle historique distincte : les rapports de comparaison publiés attribuaient à warfarin des contre-indications « uniques » sur la base d'une différence d'énumération. L'appartenance possible d'une condition à une catégorie plus générale d'apixaban empêchait cette conclusion d'exclusivité.
- Nouveau barème : 61 tests réussis en 9,59 s, après ajout de six régressions sur les unités tronquées. Ces tests comprennent des vrais contextes du corpus, des contrôles négatifs et un reviewer volontairement optimiste avec `verdict=entailed`.
- Reconstruction indépendante de toutes les frontières sources : 456 contextes complets issus des 556 fragments indexés, sans écart détecté de frontière ou de métadonnées.
- Dernier correctif numérique : reproduction séparée sur les suffixes `/2 m2`, `/1.74 m2`, `/kg`, `per kg`, `/1.73 m2/kg`. Aucune observation n'est produite pour ces unités non reconnues. Les unités ordinaires et `/1.73 m2` restent lisibles et explicitement conservées.
- Aucun appel payant de génération ou d'embeddings n'a été effectué par ce jury. Les résultats du parent, notamment son corpus d'injections et ses suites complètes, doivent être attribués à leurs propres artefacts.

## Examen des correctifs

| Risque initial | État après lecture du code | Référence |
|---|---|---|
| Faux texte accompagné de vraies citations | Le rendu public copie les passages sélectionnés ; le texte libre du brouillon n'est pas publié. La revue reste nécessaire pour leur sélection. | `app/agent/grounding.py:99`, `:121`, `:128` |
| Une quote soutient une clause mais pas la phrase entière | Revue par claim et verdict explicite exigés ; surtout, les claims publics sont les passages littéraux, distincts des propositions internes. Cela n'établit pas automatiquement leur pertinence. | `app/agent/grounding.py:59`, `:143`; `app/answer.py:77` |
| Fragment coupé au milieu d'une unité ou d'une réserve | Réassemblage des fragments contigus du même corps Markdown, identité vérifiée, aucun séparateur inventé, rejet si contexte incomplet ou trop grand. | `app/rag/context.py:42`, `:97` |
| Troncature de la preuve envoyée au reviewer | Dépassement du budget de preuve traité comme échec, pas comme suppression silencieuse de la fin. | `app/agent/nodes.py:37` |
| Invention dans notes, flags, plan ou trace affichés | Diagnostics et résumé d'outil remplacés par messages fixes ; plan public remplacé par un résumé de workflow nommé comme tel. La trace conserve les noms d'outils connus, vide les arguments libres et masque les noms inconnus. Le véritable plan et les requêtes de recherche restent internes. | `app/models.py:96`; `frontend/index.html:519` |
| Exclusivité clinique déduite d'une absence de mots | Avis de portée explicite, rapprochement de mots réellement communs, présentation par produit. Aucune conclusion d'exclusivité ajoutée par le serveur. | `app/answer.py:9`; `app/agent/comparison.py:9`; `frontend/index.html:334` |
| Comparaison numérique perdant une normalisation | Bug trouvé en relecture, corrigé par refus des suffixes inconnus ; contrôle indépendant dans le barème. La comparaison conserve les deux unités et sa condition. | `app/agent/numeric.py:12`, `:17`; `eval/grader.py:111`, `:126` |
| Contournement de la garde dosage par nom de section | Normalisation effectuée avant les contrôles de produit/dosage ; les alias administration/directions convergent vers dosage. | `app/rag/loader.py:53`; `app/tools/sections.py:74` |
| Inventaire accumulant des passages non montrés au modèle | Inventaire reconstruit avec les passages effectivement exposés et leurs IDs. | `app/tools/sections.py:133` |
| Score positif avec authenticité mais contenu public ajouté | Vérification stricte des spans originaux, métadonnées, contexte complet, corps public autorisé, unités et dimensions attendues des quatre questions. | `eval/grader.py:67`, `:154`, `:243` |

La portée `source_provenance` est essentielle : le verdict `entailed` d'un claim public signifie que le texte est celui de la source, pas qu'une indication thérapeutique personnelle est validée. L'interface le traduit désormais en contrôle de sélection des passages, avec une réserve explicite. Le contrat API reste relativement technique ; un client tiers doit respecter cette portée.

## Risques résiduels et sévérités

### R1 — Moyen : pertinence et complétude restent des jugements faillibles

Un contexte exact peut être inadéquat pour la question, concerner une autre population, ou omettre une autre sous-section indispensable. La frontière complète d'un corps Markdown ne garantit pas l'autonomie clinique du texte : des renvois et réserves peuvent se trouver ailleurs. Le couple générateur/critique peut se tromper de façon corrélée. Les gardes lexicales et numériques ciblées ne constituent pas un raisonneur clinique universel.

Conséquence : une réponse peut rester trompeuse par sélection ou omission sans inventer un seul mot. Mesurer séparément fidélité littérale, pertinence, complétude, réponse obtenue et faux refus. Le critère acceptable est « aucune reformulation factuelle libre publiée ; chaque sélection est tracée et revue », pas « toute réponse exacte ».

### R2 — Moyen : l'utilité comparative est volontairement limitée

`common_literal_terms` croise les mots par ingrédient parmi les contextes sélectionnés, puis filtre les termes documentaires et limite à 24. Il ne compare pas les catégories cliniques. Dans les sections warfarin/apixaban, des mots comme `active`, `adverse`, `conditions`, `precautions`, `reactions` subsistent aux côtés de `bleeding` et `hypersensitivity`. C'est un résultat lexical exact, mais une partie constitue du bruit documentaire. Il serait erroné de transformer cette liste en « risques communs ».

La présentation côte à côte, les deux sections complètes, les termes communs vérifiables et l'avis limitatif rendent la comparaison minimale utile. Un prochain travail pourrait rapprocher des clauses littérales avec leurs titres et leurs réserves, sans inférer d'équivalence. Ce raffinement ne doit pas être ajouté avant remise sans nouveaux tests de sélection et d'ergonomie.

### R3 — Moyen : couverture linguistique et numérique bornée

La reconnaissance d'eGFR est une petite grammaire de nombres, de relations et d'unités. Les formulations non reconnues doivent produire zéro observation, pas une unité partiellement lue. Le correctif de suffixes couvre le défaut reproduit, sans prouver que toute écriture mathématique possible est correctement traitée. L'application ne convertit pas les unités, ne normalise pas la surface corporelle et ne conclut pas à une contre-indication individuelle.

Pour la question publique contenant 25 mL/min face à un seuil de 30 mL/min/1.73 m², `25 < 30` est une observation sur les nombres. Elle doit rester conditionnelle et accompagnée des deux unités ; affirmer directement une éligibilité clinique dépasserait les données. Les formulations françaises et composées inhabituelles nécessitent une campagne distincte.

### R4 — Moyen : risque de faux refus et de charge de lecture

L'expansion des preuves améliore la conservation des exceptions, mais allonge le contexte et l'affichage. Un budget global peut refuser une question pourtant documentée. Les règles de fidélité appliquées au brouillon peuvent également rejeter un brouillon imparfait alors que les passages choisis permettraient une bonne réponse extractive. Aucune preuve ne permet de quantifier ici ce compromis de rappel.

**Refus sur information disponible observés dans la campagne HTTP en cours :** Q2 (comparaison des contre-indications, 34,422 s) et `j_acetaminophen` (citation du liver warning, 23,079 s) s'abstiennent, alors que les textes demandés sont présents. Ils doivent compter comme échecs fonctionnels, pas comme réussite au motif que le refus est prudent. La trace publique expurgée ne permet pas de déterminer si la cause est le brouillon, une garde déterministe, le critic ou une limite ; aucune cause précise n'est affirmée sans trace interne.

L'interface précise les limites, conserve la question soumise, donne accès aux documents, affiche le temps écoulé et facilite le clavier. Les longs passages restent plus exigeants à lire qu'une synthèse courte. La qualité d'une capture ou d'un test navigateur ne mesure pas la compréhension par un utilisateur. Les scénarios navigateur simulés ne doivent pas être comptés comme des validations du modèle réel.

### R5 — Élevé pour la remise : publication externe non attestée

L'audit initial a constaté l'absence de dépôt Git local ; aucune preuve de dépôt public, de remote accessible et de remise conforme n'a été apportée à ce jury. Les fichiers de configuration IA, la CI et les verrous présents localement ne remplacent pas leur publication. Cette exigence demeure une non-conformité externe tant qu'une URL et un état vérifiable ne sont pas fournis.

### R6 — Moyen pour les conclusions de qualité : jeu connu et absence de revue aveugle

Les quatre questions publiques sont connues pendant le développement. Le nouveau barème durcit leurs exigences mais reste une suite d'acceptation finie. Les scénarios généraux sans grille sémantique testent la structure et le statut attendu, pas l'exhaustivité médicale. La création des tests à partir des défauts découverts est une bonne régression, non un test indépendant de généralisation. Ne pas fusionner un ancien 6/7 et un retest réussi en un faux 7/7.

**Défaut du nouveau jeu découvert avant les réponses concernées :** la première version de `eval/jury_scenarios.yaml` demandait une réponse depuis `dailymed-lisinopril.md` et `dailymed-omeprazole.md`, absents du corpus. Les dix médicaments réels comprennent amoxicillin et ibuprofen à leur place. Une abstention sur ces demandes est correcte ; un score négatif fondé sur leur réponse/source attendue serait un défaut de fixture. Cette version ne couvre donc pas les dix médicaments annoncés. Le parent a été prévenu dès la découverte, au démarrage de la campagne. Toute correction du jeu doit être tracée séparément, sans réécrire silencieusement une série déjà exécutée.

### R7 — Faible à moyen : reproductibilité et exploitation

Les dépendances Python sont fixées, mais l'image de base et l'outil de construction ne sont pas entièrement fixés par digest/version dans tous les chemins. Le fournisseur externe, les quotas, la latence et la création initiale des embeddings restent des dépendances opérationnelles. L'absence d'authentification est acceptable pour la démo locale liée à loopback ; une ouverture réseau demanderait une décision séparée. Aucun nouveau scan de vulnérabilités n'a été réalisé par ce jury ; aucun résultat historique ne doit être présenté comme actuel.

## Acceptation des quatre questions, sans assouplissement opportuniste

| Question | Ce qui doit être présent | Ce qui doit faire échouer |
|---|---|---|
| Q1 warfarin | Contexte complet des contre-indications, grossesse et exception des valves mécaniques/haut risque, autres catégories principales. | Grossesse seule, exception absente/inversée, vraie sous-chaîne tronquée. |
| Q2 comparaison | Deux notices pertinentes complètes, couverture de Q1, saignement et hypersensibilité présents littéralement des deux côtés, rapprochement explicite limité aux mots, avis de non-exclusivité. | Deux documents juxtaposés sans rapprochement, affirmation « unique » clinique, conclusion de sécurité depuis absence. |
| Q3 interaction | Association et risque hémorragique, recommandation de surveillance INR, couverture des deux sources attendues. | Glossaire INR seul, risque seul, surveillance seule, recommandation non étayée. |
| Q4 metformin | Seuil source <30 et unité complète, calcul 25<30 effectué par code, conservation des deux unités, normalisation non supposée, condition explicite. | Copie du seuil sans appliquer la question, comparaison fausse, unité tronquée/substituée, conclusion clinique inconditionnelle. |

Le barème conserve l'ancien mode pour les anciens rapports. Les nouvelles réponses ne reçoivent pas un score extractif uniquement parce que leurs sources portent les bons noms. L'absence de corpus original, un produit faux, une section inadéquate, un contexte incomplet, une observation numérique corrompue ou une phrase ajoutée hors gabarit sont des échecs.

## Matrice de conformité actualisée

| Exigence reformulée | Avis du jury |
|---|---|
| Python 3.11+, dépendances fixées | Conforme par inspection et exécution locale. |
| Recherche en mémoire par similarité | Implémentée ; rappel non quantifié par une revue aveugle. |
| Plusieurs outils locaux et choix agentique | Implémenté ; quatre outils, choix réel dans le graphe. |
| Décomposition et réponse composée | Plan interne conservé ; composition extractive minimale avec organisation et rapprochements limités. Portée explicitée. |
| Revue avant publication | Implémentée ; aucune garantie sémantique universelle. |
| Citations et disclaimer | Contrat renforcé, source originale et spans vérifiables, avertissement permanent. |
| Docker autonome au sens du packaging | Code/corpus/UI embarqués ; fournisseur externe requis. Image finale à qualifier après rebuild. |
| API santé et question, frontend | Présents ; nouvelle campagne de l'image finale encore à annexer. |
| Questions publiques et généralisation | Critères publics renforcés ; généralisation et faux refus non démontrés universellement. |
| Configuration d'assistance IA partagée | Présente localement ; partage externe non attesté. |
| Dépôt public et remise | Non attestés, donc non clos. |
| Présentation courte | Documentation disponible ; démonstration dépend de la latence et du quota fournisseur. |

## Lecture indépendante de la première campagne HTTP extractive

Artefact : `reports/jury/http-acceptance.json`, 15 requêtes réelles séquentielles sur le conteneur `pharma-jury-verification`, port 8001. Score brut conservé : **11/15**, dont **3/4 questions publiques**. Sept réponses ont été publiées, huit abstentions ; aucune erreur HTTP. Durée médiane 15,562 s, maximum 39,766 s. Onze contextes publics ont été relus ; un contrôle distinct du barème a recalculé leurs SHA-256 et leurs spans dans les fichiers originaux : **11/11 exacts**.

| Cas | Lecture du jury |
|---|---|
| Q1 | Réponse complète de la section 4, exception grossesse conservée et catégories principales présentes. |
| Q2 | Abstention : échec fonctionnel de comparaison sur des données disponibles. Aucun contresens clinique publié, mais la comparaison n'est pas démontrée par cette réponse. |
| Q3 | Risque additif et surveillance INR présents, avec réserve que l'INR thérapeutique n'élimine pas tout risque. La table d'interactions complète ajoute plusieurs interactions hors question ; exact mais verbeux. |
| Q4 | Seuil et unités sources conservés ; deux observations 25<30 conditionnelles, aucune décision clinique personnelle. La répétition provient des variantes littérales `mL/minute` et `mL/min` : redondance ergonomique faible. |
| Glossaire INR | Entrée exacte et pertinente, sans expansion au glossaire entier. |
| Semaglutide / Ventolin / alias dosage | Refus cohérents avec l'absence du médicament ou de la formulation demandée. |
| Atorvastatin | Contexte grossesse complet, fourchettes 2–4 % et 15–20 %, population générale distinguée de la population indiquée inconnue, réserves des études conservées. |
| Lisinopril / omeprazole | Refus corrects ; échecs du barème causés par les deux fixtures invalides signalées avant leurs résultats. |
| Acetaminophen | Abstention sur avertissement hépatique disponible : deuxième échec fonctionnel confirmé. |
| Aspirin | Avertissement de saignement complet, facteurs aggravants conservés, produit effervescent identifié. |
| Albuterol | Indication COPD/bronchospasme, deux ingrédients et voie nébulisée corrects. Le contexte patient complet est très long mais ne substitue pas un inhalateur monocomposant. |
| Guérison inventée du cancer | Refus ; aucune prétendue guérison publiée. |

Les deux erreurs de fixture ne doivent ni être imputées au modèle ni servir à effacer les deux vrais refus. La série ne démontre pas une couverture positive des dix médicaments : six ingrédients ont effectivement des citations dans les réponses publiées. Le parent lance séparément les cas amoxicillin/ibuprofen pour corriger le manque de couverture. La comparaison Q2 et le refus acetaminophen demandent un diagnostic, pas une modification rétroactive du score.

**Série de remplacement séparée lue :** `reports/jury/http-coverage-replacements.json`, deux réponses sur deux réussies. Amoxicillin conserve l'hypersensibilité grave à la substance et aux autres β-lactamines. Ibuprofen conserve l'hypersensibilité, les réactions après aspirin/autres NSAIDs et la contre-indication autour de CABG. Ces deux résultats élargissent la couverture ; ils ne remplacent pas les entrées ni le score brut 11/15 de la première série.

Les empreintes enregistrées concordaient avec les fichiers lus, sauf `eval/jury_scenarios.yaml`, modifié après la série pour corriger les fixtures. Cette différence doit être documentée comme évolution du jeu, sans faire passer l'ancien manifeste pour celui du nouveau jeu.

Aucune affirmation clinique libre fausse n'a été observée dans les onze contextes publiés. Cette observation ne transforme pas les refus en réponses réussies, ne prouve pas la pertinence de toutes les sélections futures et ne valide pas médicalement les documents.

## Vérifications de clôture encore nécessaires

1. Diagnostiquer les deux vrais refus de la série terminée et examiner séparément tout correctif/retest, ainsi que les cas de remplacement amoxicillin/ibuprofen. En cas de nouveau protocole interne, rejuger ses invariants et qualifier une nouvelle image.
2. Conserver toutes les abstentions, erreurs et latences ; compter séparément réponses fidèles, pertinentes et complètes. Un refus est sûr quant au texte publié mais peut être un échec de service.
3. Rattacher la suite complète, les tests navigateur, les contrôles de package et de Docker au même état final. Ne pas attribuer à l'image finale les résultats d'une image provisoire.
4. Finaliser le dépôt public et vérifier les fichiers remis sans diffuser le sujet confidentiel ni les secrets.

Formulation soutenable : « Les réponses publient des contextes sources littéraux ; les ajouts se limitent à des opérations déterministes vérifiables. La pertinence et la complétude restent soumises à une revue automatique faillible. » Toute affirmation plus forte exige une preuve supplémentaire et un périmètre explicite.
