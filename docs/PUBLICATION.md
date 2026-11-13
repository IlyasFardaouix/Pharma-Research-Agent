# Publication et remise

Dépôt public : https://github.com/IlyasFardaouix/Pharma-Research-Agent

Branche de remise : `main`.

Le dépôt comprend le code, le corpus fourni, le frontend, le Dockerfile, les
dépendances verrouillées, les tests, les évaluations, la documentation et la
configuration d'assistance IA du projet. Il exclut les secrets, les environnements,
les caches, l'énoncé confidentiel et les artefacts générés dans `output/` et `dist/`.

`.gitattributes` conserve les octets des fichiers entre Windows et Linux : une
conversion automatique des fins de ligne changerait les SHA-256 des documents.

Les preuves de `reports/jury/` ont été enregistrées avant la publication Git.
Leur état « dépôt absent / remise non attestée » est un constat historique de
cette validation, pas un contrôle en direct de GitHub. Leurs scores et empreintes
ne sont pas réécrits après publication.

Le workflow GitHub Actions exécute les tests hors réseau à chaque push :
https://github.com/IlyasFardaouix/Pharma-Research-Agent/actions
Son résultat doit être consulté pour le commit effectivement remis ; les tests
locaux ne prouvent pas à eux seuls une exécution réussie sur GitHub.

La publication du dépôt ne transmet pas le livrable au contact recrutement.
L'énoncé demande d'envoyer le lien public et un court résumé avant le
13 novembre 2026 à 23 h 59, heure de Casablanca. Aucun email n'est envoyé par ce
projet ou par la préparation du dépôt. Vérifier l'accès public et conserver
l'identifiant du dernier commit poussé avant cette échéance.

La démonstration locale est décrite dans [DEMO.md](../DEMO.md). La présentation
de dix minutes peut prendre la forme d'un parcours de l'application et du code.
