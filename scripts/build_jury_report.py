"""Build the current French project, architecture and independent-jury report.

uv tool run --from reportlab --with pypdf python scripts/build_jury_report.py
Requires recorded jury validation; never substitutes historical results for it.
"""
from pathlib import Path
import json

from reportlab.lib.pagesizes import A4
from reportlab.platypus import Frame, Image, PageBreak, PageTemplate, Spacer
from build_report import ROOT, OUT, W, ReportDoc, Workflow, code, footer, p, plain, table


def main():
    validation = json.loads((ROOT / "reports/jury/validation.json").read_text(encoding="utf-8"))
    live = json.loads((ROOT / "reports/jury/http-focus-regraded.json").read_text(encoding="utf-8"))
    replay = json.loads((ROOT / "reports/jury/adversarial-replay.json").read_text(encoding="utf-8"))
    summary = live["summary"]
    story = []

    def page(title, *blocks):
        if story:
            story.append(PageBreak())
        story.append(p(title, "title"))
        story.extend(plain(b) if isinstance(b, str) else b for b in blocks)

    page("Pharma Research Agent",
        Spacer(1, 10), p("Comprendre le projet, son architecture et ses limites", "sub"),
        "Rapport technique et bilan du jury automatisé Astra. État du dossier local examiné le 13 novembre 2026. Le choix explicite retenu est : extraits exacts en priorité, synthèse limitée aux éléments vérifiables.",
        table(["Élément", "État observé"], [
            ("Objet", "Recherche agentique dans 21 documents locaux : 10 médicaments, deux sources et un glossaire."),
            ("Produit", "API FastAPI, graphe LangGraph, similarité NumPy, frontend autonome et conteneur Docker."),
            ("Publication", "Contextes sources littéraux, provenance, rapprochement textuel et calcul numérique conditionnel ; aucune paraphrase clinique libre du brouillon."),
            ("Vérifications nouvelles", f"{validation['offline_tests']} tests hors réseau ; {validation['browser_checks']} contrôles navigateur ; HTTP {summary['passed']}/{summary['total']} après correction de notation du barème, {live['original_summary']['passed']}/{summary['total']} brut conservé."),
            ("Limite de livraison", "Préparation locale et archive ; aucun dépôt public ni remise externe attestés."),
        ], [126, W - 126]),
        p("Démonstration technique - aucune validation clinique", "sub"),
        "Le texte reproduit ne peut pas être assimilé à une recommandation pour un patient. La sélection, la pertinence et la complétude restent faillibles. Un corpus authentique peut être ancien, incomplet ou inadapté au cas posé.",
        p("Ce rapport conserve les résultats historiques séparément des nouveaux essais. Un jury automatisé ne remplace ni un évaluateur humain ni un professionnel de santé.", "small"))

    page("01 / Le concept, simplement",
        "Le système répond à une question de recherche en consultant une collection fournie. Il ne doit pas répondre de mémoire. La difficulté consiste à trouver les bons documents, conserver les réserves, rapprocher plusieurs sources et rendre la provenance inspectable.",
        table(["Mot", "Sens concret dans ce projet"], [
            ("RAG", "Retrouver des textes, les ajouter au contexte du modèle, puis organiser une réponse documentée."),
            ("Agent", "Le modèle décide quels outils appeler et peut chercher de nouvelles preuves après une critique."),
            ("Embedding", "Vecteur numérique d'un texte ; la proximité permet de classer des passages similaires."),
            ("Critique", "Invocation séparée qui examine sujet, produit, chiffres, réserves et couverture de la question."),
            ("Extrait exact", "Texte tiré du fichier original, avec son contexte et ses positions ; pas une reformulation du modèle."),
        ], [106, W - 106]),
        "Exemple : pour définir INR, l'agent peut choisir le glossaire. Pour comparer deux notices, il récupère les deux sections. Le lecteur voit les textes sous les bonnes identités, les termes littéralement communs et une réserve sur la portée de cette comparaison.",
        "Le projet n'entraîne pas de modèle, ne met pas le corpus à jour et ne conserve pas un historique de conversation. Les questions et les passages nécessaires sont transmis au fournisseur IA configuré.",
        p("Comment lire le rapport", "sub"),
        "02-13 expliquent l'architecture et ses fichiers. 14-20 présentent la conformité, le jury, les corrections, les mesures et les limites. 21-24 préparent la démonstration, la remise et les questions techniques. Les preuves détaillées sont dans reports/jury/ et les tests.")

    page("02 / Architecture générale", Workflow(), Spacer(1, 10),
        table(["Couche", "Responsabilité"], [
            ("Interface", "Question, état d'attente, extraits, sources complètes et trace opérationnelle."),
            ("API / Runtime", "Validation, disponibilité, admission, échéance, concurrence et erreurs publiques sûres."),
            ("Agent", "Planification interne, choix des outils, focus littéraux, critique des contextes et révision bornée."),
            ("Corpus / RAG", "Métadonnées, index de fragments, réassemblage des contextes complets et provenance."),
            ("Fournisseur", "Calcul des embeddings et invocations du modèle via un endpoint compatible OpenAI."),
        ], [111, W - 111]),
        "Le paquet est autonome pour le code, les fichiers et l'interface. Il dépend néanmoins d'un fournisseur réseau pour les fonctions IA. Aucune base vectorielle externe n'est requise.")

    page("03 / Une question de bout en bout",
        table(["Étape", "Transformation"], [
            ("Réception", "POST /ask : corps borné avant parsing ; question de 1 à 4 000 caractères non blancs."),
            ("Admission", "L'index doit être prêt et une place de worker disponible ; un délai et une annulation sont attachés au travail."),
            ("Planification", "Le modèle propose un plan de recherche. Ce plan reste interne ; le public reçoit un résumé serveur neutre des étapes."),
            ("Recherche", "Le modèle choisit ses outils. Les fragments trouvés servent à repérer des contextes sources complets."),
            ("Sélection", "JSON interne : focus de 12 à 1 800 caractères copié littéralement, avec un seul identifiant de contexte par sélection."),
            ("Revue", "Contrôles de structure et de fidélité ciblés, puis critique sémantique explicite entailed / contradicted / insufficient."),
            ("Révision", "L'agent peut reformuler ou rechercher d'autres preuves, dans des limites d'appels, temps, texte et itérations."),
            ("Publication", "Seuls les contextes sélectionnés et revus sont reproduits littéralement ; sinon abstention fixe. Calculs et notes de portée sont maîtrisés par le serveur."),
        ], [100, W - 100]),
        "La trace des outils montre les opérations effectuées. Elle n'est pas un accès au raisonnement interne complet du modèle et n'est pas une preuve de vérité médicale.")

    page("04 / Corpus et identité du produit",
        "Le dossier contient dix notices DailyMed, dix monographies MedlinePlus et un glossaire. Les 21 sources originales restent inchangées. Leur nom de fichier identifie un sujet, mais ne garantit pas la formulation, la combinaison ni la voie d'administration.",
        table(["Métadonnée", "Utilité"], [
            ("drug / source / file", "Identifier l'ingrédient, la famille documentaire et le document original."),
            ("product / product_id", "Décrire les identités particulières attestées par le corpus ; registre partiel, pas catalogue universel."),
            ("section / subsection", "Conserver la rubrique et les sous-rubriques des titres Markdown."),
            ("document_sha256", "Empreinte des octets du fichier, pour détecter un document modifié."),
            ("start_offset / end_offset", "Positions dans le texte UTF-8 décodé, en caractères Unicode, pas en octets."),
            ("raw_text", "Sous-chaîne exacte du fichier, sans réécriture, normalisation ou traduction."),
        ], [143, W - 143]),
        "Cas important : le fichier albuterol de DailyMed décrit une association ipratropium + albuterol pour nébulisation, tandis que MedlinePlus couvre des formes orales. Ces documents ne documentent pas automatiquement un inhalateur Ventolin à ingrédient unique.",
        "Les alias aident à rechercher un ingrédient ; ils ne prouvent pas l'interchangeabilité des produits. Une demande de dosage ambiguë doit préciser un produit attesté ou conduire à un refus.")

    page("05 / Du fragment au contexte complet",
        "Les 556 fragments de l'index restent courts pour les embeddings. Avant cette correction, une phrase pouvait être coupée au milieu d'une quantité : la notice atorvastatin finissait un fragment par « is 2 », puis le suivant commençait par « to 4% and 15 to 20%, respectively ».",
        "Le nouveau module rag/context.py traite le fragment comme un localisateur. Il rassemble le corps complet de la rubrique Markdown, avant de le montrer au modèle et au critique. Il conserve tous les caractères du texte source, sans séparateur inventé.",
        table(["Contrôle", "Comportement"], [
            ("Continuité", "Aucun trou, chevauchement ou fragment final manquant n'est admis."),
            ("Identité", "SHA, document, titres et produit doivent être cohérents dans tous les fragments."),
            ("Nouvel identifiant", "Le contexte reçoit son propre span entier et un identifiant canonique correspondant."),
            ("Budget", "Un contexte trop grand est refusé explicitement ; il n'est pas tronqué silencieusement."),
            ("Déduplication", "Un même contexte récupéré plusieurs fois est publié une fois, en conservant son meilleur score."),
            ("Cache", "Les 556 textes et IDs d'index restent strictement identiques ; pas de recalcul des embeddings causé par ce changement."),
        ], [119, W - 119]),
        code("document@sha256-sur-12-caracteres:debut-fin\nExemple corrigé atorvastatin : 25611-30345\n4 734 caractères sources au lieu d'un fragment de 1 924 caractères."),
        "Une rubrique complète peut renvoyer à une autre rubrique. Le réassemblage ne garantit donc pas que tous les contextes cliniques nécessaires aient été sélectionnés : l'agent et la revue doivent encore les rechercher.")

    page("06 / Embeddings, index et cache",
        "Chaque texte d'indexation devient un vecteur. Les vecteurs de documents et de question doivent provenir d'un espace compatible. Après normalisation L2, le produit scalaire donne une similarité cosinus. La similarité est un indice de recherche, jamais un jugement médical.",
        code("V = normaliser(embeddings(textes_des_fragments))\nq = normaliser(embedding(question))\nscores = V @ q\nfiltrer et classer les meilleurs fragments\nréassembler les contextes sources avant exposition"),
        "Pour 556 lignes, NumPy suffit : mémoire et opérations sont de l'ordre de N × D. Une base vectorielle ajouterait ici un service à déployer sans bénéfice démontré. Un corpus beaucoup plus grand demanderait de mesurer à nouveau ces choix.",
        "Le cache NPZ dépend des textes, du modèle, de l'endpoint, des dimensions et d'une version explicite. Forme, valeurs finies et normes sont vérifiées. Les écritures sont atomiques avec temporaires uniques et reprises bornées pour certains verrouillages Windows.",
        "Sans dimensions déclarées, une courte requête vérifie les dimensions avant réutilisation. Une dimension identique ne prouve pas que le sens du déploiement n'a pas changé : EMBEDDING_CACHE_VERSION doit évoluer si nécessaire.",
        "TOP_K=5 et MIN_RELEVANCE=0,18 sont des heuristiques configurables. Leur rappel n'est pas calibré sur un large jeu indépendant. Les recherches par section sont complémentaires ; elles ne remplacent pas la recherche sémantique imposée par le sujet.")

    page("07 / Quatre outils, choisis par l'agent",
        table(["Outil", "Fonction et précaution"], [
            ("search_corpus", "Recherche sémantique query / k / drug ; filtre les scores faibles puis expose les contextes complets."),
            ("get_drug_section", "Rubrique déterministe par ingrédient, source et produit. Repli explicite seulement ; normalisation de section avant les politiques de dosage."),
            ("lookup_glossary", "Entrée lexicale attestée ; aucun terme absent inventé. Une entrée est déjà un contexte complet."),
            ("list_drugs", "Inventaire, identité des produits et preuves d'identité avec IDs visibles, pour définir le périmètre."),
        ], [129, W - 129]),
        "registry.py expose les schémas ; le modèle choisit et émet les appels. Le code ne route pas les quatre questions publiques vers des réponses préparées. Les gardes déterministes encadrent les arguments et les produits, indépendamment du choix de recherche.",
        "Défaut reproduit : demander « administration » ou « DOSAGE AND ADMINISTRATION » pouvait contourner une garde qui ne reconnaissait que « dosage ». La section est désormais canonisée en amont, à l'aide d'une liste explicite d'alias. Une rubrique inconnue ne retombe plus sur une recherche de sous-chaîne arbitraire.",
        "L'inventaire stockait des preuves sans en donner les IDs au générateur. Il expose maintenant les identifiants et les extraits d'identité nécessaires pour les citer. Les budgets de contexte restent applicables.")

    page("08 / Contrats de publication",
        table(["Contrat", "Exigence"], [
            ("DraftAnswer interne", "Au plus 20 sélections. Chaque text est un focus littéral de 12 à 1 800 caractères dans un seul contexte récupéré ; IDs uniques."),
            ("ClaimReview", "Une revue par affirmation ; verdict explicite entailed, contradicted ou insufficient ; preuves littérales de tous les passages déclarés."),
            ("Réponse publique", "response_mode=source_excerpts ; chaque claim est le contexte brut entier, avec une citation unique et une égalité exacte claim.text == citation.excerpt."),
            ("Grounding", "scope=source_provenance ; indique la portée de la vérification. Le verdict ne certifie pas l'applicabilité clinique."),
            ("Abstention", "Aucun claim, citation ou calcul ; motif et explication serveur fixes ; aucun brouillon ni note clinique du reviewer."),
        ], [130, W - 130]),
        "Le focus sert à localiser une information et non à rédiger une conclusion clinique. Il peut être partiel ; le critique examine les contextes entiers sélectionnés, et le public reçoit ces contextes avec leurs réserves. Un texte reformulé est refusé par le contrôle de sous-chaîne exacte.",
        "Les diagnostics libres du critique sont internes. Les notes publiques et warnings proviennent de messages fixes. Le plan public est libellé Workflow summary. La trace conserve les vrais noms d'outils ; requêtes libres, arguments et résumés partiels restent internes pour ne pas réintroduire une hypothèse clinique non vérifiée.",
        "La fidélité du texte est une propriété contrôlable. La pertinence, la bonne sélection des sections et la complétude demeurent des jugements faillibles, en particulier si le critique se trompe. Cette distinction doit rester visible dans l'interface et à l'oral.")

    page("09 / Synthèse strictement bornée",
        p("Comparaison documentaire", "sub"),
        "Le serveur peut placer les contextes des deux médicaments côte à côte. Il calcule une intersection de mots littéraux non triviaux, après retrait de mots documentaires génériques. Chaque terme commun doit réellement apparaître dans les textes de chaque ingrédient.",
        "Cette observation lexicale aide le lecteur à rapprocher les libellés. Elle n'établit ni l'équivalence clinique de deux catégories ni une contre-indication exclusive à un médicament. L'absence d'une condition dans une liste ne permet pas d'inférer une permission de traitement.",
        p("Comparaison numérique conditionnelle", "sub"),
        "Un petit module Decimal reconnaît une valeur eGFR explicite dans la question et un seuil explicite dans le contexte. Il calcule below, equal ou above, conserve les deux unités et ajoute une réserve fixe sur les unités, la normalisation et la population.",
        "Dans la question publique, 25 est numériquement inférieur à 30. Mais mL/min dans la question et mL/min/1,73 m² dans la notice ne deviennent pas silencieusement la même grandeur. Ce calcul ne statue donc pas sur l'éligibilité clinique du patient.",
        "Si le nombre, le seuil ou l'unité manquent, ou si plusieurs valeurs distinctes sont présentes, aucun calcul n'est produit. Le brouillon ne peut pas imposer une fausse relation numérique dans cette sortie.",
        "Ces deux synthèses sont limitées et vérifiables. Elles ne constituent pas un moteur général d'interprétation des médicaments, de conversion d'unités ou de décision clinique.")

    page("10 / Revue, révision et refus",
        "Le critique lit les focus et les preuves complètes. Il examine la pertinence de chaque contexte sélectionné, sujet, produit, voie, population, quantités, unités, négations, exceptions et couverture de toutes les parties par les contextes qui seront publiés. Une preuve récupérée mais non sélectionnée ne remplit pas une partie manquante.",
        "Le verdict entailed est nécessaire, mais pas une preuve mathématique de vérité : il est produit par un modèle. Par défaut, générateur et critique utilisent le même modèle dans des invocations séparées ; leurs erreurs peuvent être corrélées.",
        table(["Situation", "Issue"], [
            ("Défaut réparable", "Le code ou la revue renvoie des motifs ; l'agent peut chercher de nouvelles preuves et réviser, au plus deux fois par défaut."),
            ("Revue mal formée", "Échec fermé : aucune publication du brouillon ; révision ou abstention."),
            ("Produit ou sujet absent", "Refus fixe, sans substitution de dosage d'une autre formulation."),
            ("Budget dépassé", "Arrêt borné et refus de publier des résultats incomplets non approuvés."),
            ("Panne fournisseur", "Erreur HTTP publique expurgée ; aucune réponse médicale de secours inventée."),
        ], [123, W - 123]),
        "Les anciennes gardes de paraphrase aident à corriger un focus non littéral. Elles ne rejettent plus un vrai focus pour plusieurs phrases ou pour une réserve située ailleurs dans son contexte public complet. Le calcul numérique séparé reste strict. Ces règles ne constituent pas un moteur universel d'implication sémantique.")

    page("11 / Runtime, API et sécurité locale",
        table(["Protection", "Effet"], [
            ("Corps de requête", "16 Kio avant parsing, y compris transfert en morceaux ; réception limitée à 10 secondes."),
            ("Travail concurrent", "Deux travaux par processus par défaut ; place conservée jusqu'à la fin réelle d'un worker interrompu."),
            ("Délais", "45 s par appel et 180 s par réponse par défaut ; chaque appel respecte le temps restant."),
            ("Budgets", "16 invocations modèle, 24 outils, 4 096 tokens de sortie, 60 000 caractères de preuves et 100 000 de contexte par défaut."),
            ("GET /health", "HTTP 200 ; état ok / starting / degraded. Signale l'index et la configuration, pas un test permanent du fournisseur."),
            ("POST /ask", "Question JSON ; réponse structurée, extraits, citations, calcul éventuel, disclaimer et trace."),
            ("GET /sources/{file}", "Texte brut du seul corpus, empreinte SHA obligatoire ; 409 si le fichier a changé, 404 pour chemin non autorisé."),
        ], [131, W - 131]),
        "La route de source interdit traversée et liens symboliques sortants, ne sert pas .env, impose text/plain, nosniff et une politique sandbox. Le navigateur ouvre uniquement un lien local avec nom et empreinte contrôlés.",
        "Annuler une requête ne tue pas rétroactivement un appel réseau dans un thread. Les contrôles sont coopératifs et le timeout SDK borne normalement l'attente. Une isolation plus forte exigerait des workers supervisés.")

    page("12 / Justification des choix",
        table(["Choix", "Bénéfice et coût"], [
            ("Python 3.11", "Base cohérente pour Docker, tests et CI ; dépendances verrouillées par versions et hashes."),
            ("FastAPI / Pydantic", "Contrats visibles, validation et tests injectables. La validation structurelle ne prouve pas la vérité des textes."),
            ("LangGraph", "Boucle de revue explicite, étapes observables ; davantage de dépendances qu'une boucle Python simple."),
            ("NumPy en mémoire", "Adapté au petit corpus, sans service vectoriel ; performances à remesurer à grande échelle."),
            ("Contextes après recherche", "Conserve l'index et son cache ; évite d'exposer des phrases coupées ; augmente le coût du contexte et de la revue."),
            ("Publication extractive", "Écarte la paraphrase inventée de la sortie ; textes plus longs, moins fluides, pertinence toujours à vérifier."),
            ("HTML autonome", "Frontend embarqué, pas de bundler ; une application plus grande bénéficierait d'une structuration différente."),
            ("Pas d'historique", "Réduit les données conservées par l'application ; pas de conversation suivie ni d'audit multi-utilisateur."),
            ("Docker non root", "Paquet code/corpus/UI reproductible dans son périmètre ; le tag de base reste mutable et le fournisseur externe."),
        ], [136, W - 136]),
        "Le choix extractif répond à la préférence explicite de l'utilisateur et conserve le cœur agentique : planifier, choisir ses outils, sélectionner, rapprocher et faire revoir les preuves. Une abstention systématique ou un dump de tous les documents n'aurait pas la même utilité.")

    page("13 / Les fichiers à comprendre",
        table(["Fichier / dossier", "Responsabilité"], [
            ("main.py / runtime.py", "Routes, cycle de vie, pool, admission, annulation et erreurs."),
            ("config.py / execution.py", "Configuration de l'environnement, limites et budgets propres à la requête."),
            ("answer.py / models.py", "Contrats métier stricts, réponse publique, cohérence et diagnostics publics maîtrisés."),
            ("rag/loader.py", "Titres, fragments, provenance, identité des produits, alias de sections et sélection structurée."),
            ("rag/context.py", "Réassemblage exact des corps de rubrique avant exposition aux modèles."),
            ("rag/embeddings.py / index.py", "Client, cache, normalisation et vraie similarité cosinus en mémoire."),
            ("tools/", "Schémas, gestionnaires, formatage des contextes et citations."),
            ("agent/nodes.py / graph.py", "Étapes et transitions, révisions, wrapper des appels et budgets."),
            ("agent/grounding.py", "Vérifications de revue et frontière de publication extractive."),
            ("agent/fidelity.py / policies.py", "Contrôles de régression limités ; pas d'oracle clinique général."),
            ("agent/numeric.py / comparison.py", "Arithmétique conditionnelle et intersection de mots littéraux."),
            ("app/eval.py / eval/", "Barème historique, nouveau barème extractif et scénarios ; jamais du routage de réponses."),
            ("tests/ / scripts/", "Tests hors réseau, navigateur, campagne HTTP, replays, captures, PDF et archive."),
        ], [174, W - 174]))

    page("14 / Dossier complet et conformité",
        "L'audit porte aussi sur le corpus, les documents, les exclusions, la configuration, Docker, les preuves d'essai et le paquet. Les environnements installés et caches sont des artefacts locaux ; leur présence ne doit pas les faire entrer dans une remise propre.",
        table(["Exigence / élément", "Bilan"], [
            ("Python et dépendances fixées", "Présents, avec verrous de hashes. Installation et tests de référence sous Python 3.11."),
            ("Plan, similarité mémoire, outils autonomes", "Implémentés dans le graphe ; quatre outils, sans imposer deux outils à chaque question simple."),
            ("Critique, citations, disclaimer", "Implémentés, renforcés ; portée source_provenance explicite, jugement sémantique encore faillible."),
            ("Docker, /health, /ask, frontend", "Présents ; nouvelle construction et contrôles rattachés aux preuves jury."),
            ("Questions composées", "Comparaisons documentaires, interactions et seuils ; succès mesurés séparément des refus et de la fidélité textuelle."),
            ("Configuration d'assistance IA", ".claude/ conserve instructions, plan et transparence. Présente localement, pas encore poussée."),
            ("Secret et énoncé confidentiel", ".env et sujet exclus ; .env.example sans secret ; sélection explicite et scan de la clé courante avant ZIP."),
            ("CI distante", "Workflow GitHub présent ; exécution distante non attestée. Présence du fichier n'est pas preuve de réussite."),
            ("Dépôt public / commit remis", "Non satisfait localement : dossier non Git lors du jury et aucune URL publique attestée."),
            ("Présentation", "Guide de démo simple et trame de dix minutes dans DEMO.md."),
        ], [167, W - 167]),
        "L'archive ne remplace pas la remise externe exigée. Aucun email de remise ni publication publique n'a été effectué dans cet audit.")

    page("15 / Ce que le jury a réellement trouvé",
        "Le jury automatisé Astra a audité dans un contexte séparé. Deux revues parallèles ont examiné le grounding et l'interface. Astra a ensuite contribué au barème et à ses tests : cette relecture n'est donc pas une évaluation externe aveugle. Les constats initiaux sont conservés comme état avant corrections.",
        table(["Gravité", "Défaut démontré"], [
            ("Élevée", "Une réponse réelle déduisait une contre-indication propre à warfarin de son absence d'énumération dans l'autre notice. Une catégorie générale pouvait pourtant couvrir le cas précis."),
            ("Élevée", "Avec un critique volontairement optimiste, citation réelle et SHA valides laissaient passer exception inversée, unité L au lieu de mL et bénéfice cancer inventé."),
            ("Élevée", "La garde de grossesse cherchait des mots sans vérifier suffisamment le sens de l'exception."),
            ("Élevée", "Des alias de rubrique contournaient la garde de dosage d'un produit non documenté."),
            ("Moyenne", "Un découpage réel coupait une quantité ; d'autres fragments séparaient impact clinique et intervention d'un tableau."),
            ("Moyenne", "L'inventaire conservait des preuves sans montrer leurs IDs au générateur."),
            ("Qualité", "L'ancien barème pouvait attribuer PASS à des phrases matériellement fausses, malgré ses contrôles d'offsets corrects."),
            ("Remise", "Le dossier n'était pas un dépôt Git et aucun dépôt public soumis n'était attesté."),
        ], [87, W - 87]),
        "Une injection de critique défaillant démontre une limite de la barrière, pas une fréquence d'attaque réelle du modèle. La comparaison erronée observée dans des rapports réels est une preuve distincte de contresens sémantique.")

    page("16 / Corrections et preuves associées",
        table(["Correction", "Vérification"], [
            ("Sortie littérale", "Le texte du brouillon n'entre plus dans les faits publics ; tests avec critique optimiste et verdict entailed explicite."),
            ("Contexte complet", "Continuité, SHA, identité, nouveaux spans, Unicode/CRLF, déduplication, fragment manquant et dépassement de limite testés."),
            ("Dosage / alias", "Canonisation avant la politique ; variantes de casse, ponctuation, intitulés numérotés et MedlinePlus testées."),
            ("Exception et unités", "Régressions ciblées renforcées ; calcul avec unités explicites ; suffixes inconnus /kg ou /1,74 m² rejetés au lieu d'être ignorés."),
            ("Comparaison", "Restriction à la formulation des notices ; mots communs calculés littéralement et aucune inférence d'exclusivité clinique."),
            ("Évaluation", "Contrat extractif séparé du barème de prose ; relecture des spans depuis le fichier et couverture renforcée des quatre questions publiques."),
            ("Diagnostics", "Notes, flags et plan public ne recopient pas une conclusion médicale libre ; motifs publics fixes."),
            ("Sources complètes", "Téléchargement local lié à SHA, texte brut protégé ; hash différent et traversées rejetés."),
        ], [148, W - 148]),
        f"Replay actuel : {replay['summary']['protected']}/{replay['summary']['total']} phrases falsifiées absentes du résultat public ; {replay['summary']['abstained']} refus. Les autres cas ne publient que leur contexte original. Cela mesure la fidélité textuelle dans ces cas, pas la pertinence médicale de toute sélection.",
        "Les fichiers de preuve sont conservés dans reports/jury/. Les résultats initiaux restent identifiés comme antérieurs ; aucune ancienne erreur n'est effacée en changeant son score après coup.")

    page("17 / Expérience utilisateur",
        table(["Défaut initial", "Comportement corrigé"], [
            ("Question / réponse désynchronisées", "Rappel de la question soumise, exemples bloqués pendant l'appel et résultat lié à la demande d'origine."),
            ("Source non ouverte au clic", "Le lien ouvre l'extrait, y déplace le focus et permet aussi de lire le fichier complet lié à son empreinte."),
            ("Instructions internes visibles", "Warnings et notes publics maîtrisés ; aucun conseil de correction clinique du reviewer recopié."),
            ("Limite de saisie tardive", "Compteur de 4 000 points de code, contrôle avant POST, collage conservé sans troncature silencieuse."),
            ("Attente opaque", "Temps écoulé, limite et annulation ; aucune fausse progression de recherche simulée."),
            ("Preuves difficiles à lire", "Identité médicament / produit / section, texte exact avec retours à la ligne, comparaison en colonnes sur grand écran."),
            ("Accessibilité", "Titres cohérents, focus après réponse / erreur / source, annonces courtes et absence de débordement mobile vérifiée."),
            ("Réponse incohérente", "En mode extractif, un claim différent de l'extrait ou lié à une source ambiguë n'est pas affiché."),
        ], [145, W - 145]),
        "Les contrôles Edge interceptent les appels /ask pour tester les états sans coût fournisseur. Les captures réelles et la campagne HTTP sont des preuves séparées. Une vérification humaine au lecteur d'écran reste à faire.",
        "L'interface est orientée vers la lecture de preuves, avec une réserve explicite sur la pertinence et la complétude. Elle ne présente pas un badge vert comme une certification clinique.")

    page("18 / Résultats de la nouvelle campagne",
        table(["Niveau", "Mesure et portée"], [
            ("Tests hors réseau", f"{validation['offline_tests']} réussis. Contrats, graphe, API, concurrence, cache, outils, source download, contexte et mutations. Fournisseur simulé ou absent."),
            ("Navigateur", f"{validation['browser_checks']} contrôles réussis sur l'interface livrée. Réponses interceptées sauf contrôles HTTP sans génération."),
            ("Replay adversarial", f"{replay['summary']['protected']}/{replay['summary']['total']} phrases inventées non publiées, critique défaillant injecté."),
            ("HTTP + fournisseur réel", f"{summary['passed']}/{summary['total']} cas acceptés par le nouveau barème ; {summary['abstained']} refus ; {summary['http_errors']} erreurs HTTP."),
            ("Docker", validation['docker_summary']),
            ("Intégrité", "Empreintes du corpus et des fichiers livrés enregistrées ; cache d'index conservé sans modification des 556 textes."),
        ], [125, W - 125]),
        "Les refus attendus comptent parmi les réussites de scénarios négatifs. Ils ne doivent pas être confondus avec un taux de réponse aux questions positives. Les questions générales testent surtout structure, sources et statut ; leur sens demande aussi une lecture.",
        "Le barème extractif vérifie le contexte entier depuis la source, l'identité documentaire et produit, les relations numériques et le texte public hors extraits. Les questions publiques ajoutent des critères de complétude. Ce n'est ni un diagnostic médical ni un jeu de test aveugle externe.",
        "Les 15 appels ont utilisé l'image focus. L'image finale a ensuite embarqué le barème corrigé : les empreintes confirment app, frontend et corpus identiques, seule eval/grader.py diffère. Contrôles HTTP et capture réelle ont été rejoués sur le conteneur final.",
        "Le nombre fini de cas, un fournisseur et une configuration donnés ne démontrent pas l'absence de toutes les failles. Les empreintes et la date permettent de savoir quelle version a réellement été éprouvée.")

    page("19A / Détail des appels réels",
        table(["Scénario", "Issue du contrôle", "Durée"], [
            (r['id'], "PASS" if r['score']['ok'] else "FAIL", f"{r['duration_seconds']:.1f} s")
            for r in live['results']
        ], [W - 163, 91, 72]),
        p(f"Latence médiane : {validation['latency_seconds']['median']:.1f} s ; maximum : {validation['latency_seconds']['maximum']:.1f} s. Mesures locales, pas un engagement de performance future.", "small"),
        p("Lire les erreurs sans les masquer", "sub"),
        *([f"{r['id']} : " + "; ".join(r['score']['failures']) for r in live['results'] if not r['score']['ok']]
          or ["Aucun échec dans cette campagne enregistrée. Une répétition peut changer la réponse, le refus ou la latence du modèle."]),
        f"Score brut : {live['original_summary']['passed']}/{summary['total']}. Un faux négatif Q4 provenait d'une parenthèse de (eGFR) non reconnue par le barème. Le seuil, l'unité complète et le calcul conditionnel étaient présents. Le correctif de notation a été testé sans supprimer les négatifs, puis les mêmes réponses ont été réévaluées sans nouvel appel. Les scores initiaux restent conservés.")
    page("19B / Incidents et retests",
        table(["Phase", "Résultat", "Interprétation"], [
            ("Ancienne prose", "6/7", "Un score selon l'ancien barème pouvait conserver une erreur sémantique."),
            ("Premiers extraits", "11/15", "Deux vrais refus et deux erreurs de préparation du jeu."),
            ("Couverture corrigée", "2/2, séparément", "Amoxicillin et ibuprofen, sans effacer les cas invalides initiaux."),
            ("Focus littéraux", "14/15 brut", "Une réponse correcte rejetée par un défaut de notation du barème."),
            ("Mêmes réponses relues", "15/15", "Correction de eGFR) ; aucun nouvel appel ni critère retiré."),
        ], [110, 94, W - 204]),
        "Historique distinct : ancienne prose à 6/7, puis première version extractive à 11/15. Cette dernière comprenait deux erreurs de préparation (lisinopril et omeprazole absents) et deux vrais refus sur données présentes (comparaison et acetaminophen). Les remplaçants amoxicillin et ibuprofen ont réussi séparément 2/2. La friction d'une paraphrase interne ensuite jetée a motivé les focus littéraux. Aucune série n'est réécrite ni fusionnée en faux score parfait.",
        "Un scan Python antérieur recensait 54 dépendances sans vulnérabilité connue signalée à cet essai. Il n'est pas un nouveau scan de cette campagne et ne couvre ni l'image système complète ni les erreurs de logique. Aucun avis de sécurité global n'en est déduit.")

    page("20 / Limites encore ouvertes",
        table(["Limite", "Conséquence et action raisonnable"], [
            ("Sélection / complétude", "Un extrait exact peut être hors sujet ou omettre une réserve dans une autre rubrique. Constituer des cas aveugles et une annotation indépendante."),
            ("Corpus figé", "Actualité et exhaustivité non garanties ; registre de produits partiel. Prévoir versions et validation des mises à jour."),
            ("Revue corrélée", "Même modèle par défaut pour génération et critique ; diversifier ne fournit pas une garantie universelle."),
            ("Faux refus / coût", "Les gardes et contextes longs peuvent augmenter refus et latence ; mesurer le compromis sur des cas positifs distincts."),
            ("Extraits trop larges", "Des réponses réelles conservent une grande table d'interactions ou un dosage albuterol au-delà du besoin. Réduire la sélection en gardant ses réserves améliorerait la lecture."),
            ("Fournisseur", "Réseau, quota et disponibilité externes. Des 429 et délais ont été observés historiquement ; /health ne les anticipe pas tous."),
            ("Exposition Internet", "Pas d'authentification ni de quota utilisateur. Garder localhost ; une ouverture publique demande TLS, identité et limites globales."),
            ("Confidentialité", "Questions et textes partent au fournisseur ; ne pas utiliser de données de patients dans cette démo."),
            ("Reproductibilité", "Tag Python de base mutable, CI distante non attestée, quotas par processus, pas de verrou distribué du cache."),
            ("Accessibilité", "Tests automatisés et visuels limités ; essai humain au clavier et lecteur d'écran encore utile."),
            ("Remise externe", "Créer / vérifier un dépôt autorisé, contrôler les fichiers suivis, pousser un commit et remettre l'URL selon le sujet."),
        ], [138, W - 138]),
        "Le contrat tenu est la reproduction contrôlée de sources, accompagnée de synthèses bornées. Une garantie générale de zéro hallucination ou de sécurité clinique ne serait pas justifiée.")

    page("21 / Démo simple, puis dix minutes",
        p("Pour tester immédiatement", "sub"),
        "Ouvrir http://127.0.0.1:8000, attendre l'état prêt, puis demander « Define INR using only the provided local glossary. ». Cliquer sur la source, lire l'extrait et ouvrir le document complet. Ne jamais afficher la clé .env dans une démonstration.",
        table(["Durée", "Démonstration"], [
            ("0-2 min", "Présenter le besoin, le corpus fixe et le graphe ; distinguer recherche documentaire et décision clinique."),
            ("2-3 min", "Définir INR ; montrer source, passage littéral et trace des outils."),
            ("3-5 min", "Comparer warfarin/apixaban ; lire les deux notices, mots communs et réserve sur l'exclusivité clinique."),
            ("5-7 min", "Question metformin/eGFR ; montrer seuil, unités de chaque côté et calcul conditionnel, sans décision personnalisée."),
            ("7-8 min", "Demander le dosage d'un inhalateur Ventolin absent : expliquer le refus de substituer une autre formulation."),
            ("8-10 min", "Montrer mesures, replays, limites restantes et état de remise du dépôt."),
        ], [84, W - 84]),
        "Préparer le conteneur et l'index avant le créneau. Les appels composés peuvent durer longtemps. Si le fournisseur échoue, présenter un résultat enregistré en l'annonçant comme tel, plutôt que simuler une réponse en direct.",
        "DEMO.md contient les commandes PowerShell, les questions et la marche de secours. Le rapport et les captures permettent de présenter le fonctionnement sans exposer de données sensibles.")

    page("22 / Installation et produit remis",
        code("# Depuis le dossier livré, configurer .env avec ses propres accès\ndocker build -t agent .\ndocker run --rm -p 127.0.0.1:8000:8000 --env-file .env agent\n# Ouvrir http://127.0.0.1:8000 et attendre status=ok"),
        "Le premier démarrage calcule les embeddings avec un accès réseau. Un volume monté sur /app/.cache permet de garder l'index entre conteneurs. Les valeurs OPENAI_MODEL et OPENAI_EMBEDDING_MODEL doivent être autorisées par le fournisseur choisi.",
        code("# Tests locaux hors réseau\n.venv311/Scripts/python.exe -B -m pytest -p no:cacheprovider\n# Régression adversariale sans fournisseur\n.venv311/Scripts/python.exe -B scripts/adversarial_replay.py\n# Navigateur Edge, génération interceptée\nuv tool run --from playwright python scripts/browser_smoke.py"),
        "L'archive contient code, corpus, tests, documents, captures, rapport et preuves sélectionnées. MANIFEST_SHA256.json permet de contrôler chaque fichier. Les environnements, caches, secrets, fichiers temporaires et énoncé confidentiel sont exclus.",
        "La sélection de paquet vérifie l'absence de la clé courante, sans prétendre détecter tout secret possible. Avant publication Git, il faut aussi inspecter les fichiers suivis : .gitignore seul n'est pas une preuve de propreté.",
        "Le produit est préparé pour la démonstration locale dans le périmètre documenté. La conformité de la remise externe reste distincte, faute de dépôt public et de commit soumis attestés.")

    screenshot = Image(str(ROOT / "output/preview/desktop.png"))
    image_scale = min(W / screenshot.imageWidth, 530 / screenshot.imageHeight)
    screenshot.drawWidth = screenshot.imageWidth * image_scale
    screenshot.drawHeight = screenshot.imageHeight * image_scale
    page("23 / Aperçu réel du produit",
        "Capture d'une réponse réelle sur le conteneur de cette version. Les contrôles navigateur à réponses interceptées sont enregistrés séparément.",
        screenshot, Spacer(1, 8),
        "L'aperçu ordinateur et la capture mobile sont livrés séparément en PNG pour une lecture à pleine résolution. La preuve JSON conserve la vraie réponse et l'empreinte du frontend.")
    page("24 / Comprendre et défendre le projet",
        p("Ordre conseillé de lecture du code", "sub"),
        "README et ARCHITECTURE ; answer.py et models.py ; grounding.py ; nodes.py et graph.py ; loader.py, context.py, embeddings.py et index.py ; runtime.py et main.py ; enfin les tests qui démontrent ces frontières.",
        table(["Question de jury", "Réponse à comprendre"], [
            ("Pourquoi un agent ?", "Il choisit les outils, assemble les preuves nécessaires et peut relancer une recherche après critique, dans un graphe borné."),
            ("Pourquoi NumPy ?", "556 vecteurs restent petits : calcul cosinus en mémoire, sans service vectoriel externe. Ce choix doit être remesuré à grande échelle."),
            ("Pourquoi garder le critique ?", "Le texte peut être exact et hors sujet. Le critique juge pertinence, produit et couverture des contextes entiers."),
            ("Pourquoi un focus exact ?", "Il localise le sujet sans demander une paraphrase ensuite jetée. Il ne remplace jamais le contexte complet public."),
            ("Qu'est-ce qui est garanti ?", "La copie contrôlée de sources dans le périmètre testé ; pas la vérité clinique, la pertinence parfaite ou la complétude universelle."),
            ("Remise : étape restante ?", "Un dépôt public et un commit effectivement soumis ; le ZIP local ne les remplace pas."),
        ], [128, W - 128]),
        p("Sources et méthode", "sub"),
        "Sources primaires : dossier de projet, corpus original, configuration expurgée, énoncé confidentiel consulté sans le redistribuer, rapports JSON de la campagne, audit Astra indépendant et preuves UX. Les critiques initiales et les corrections sont conservées dans reports/jury/.",
        "Les essais sont reproductibles par commandes, mais les réponses du fournisseur restent variables. Une absence de défaut observé est une observation bornée, jamais une preuve que toutes les failles possibles ont disparu.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = ReportDoc(str(OUT), pagesize=A4, leftMargin=47, rightMargin=47, topMargin=58, bottomMargin=60,
        title="Pharma Research Agent - Architecture et bilan du jury", author="Projet assignment-pharma",
        subject="Architecture, audit, corrections, validation et démonstration")
    doc.addPageTemplates(PageTemplate(id="report", frames=Frame(47, 60, W, A4[1] - 118,
        id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0), onPage=footer))
    doc.build(story)
    print(f"Created {OUT.name}")


if __name__ == "__main__":
    main()
