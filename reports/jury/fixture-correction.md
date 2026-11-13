# Erreur de préparation du jeu : conservée et corrigée

La première campagne HTTP a été lancée avec deux attentes erronées du préparateur :
`j_lisinopril` et `j_omeprazole` demandaient une réponse citant des fichiers absents.
Le jury Astra a signalé cette erreur pendant la campagne, avant lecture de leurs
résultats. La liste réellement présente contient amoxicillin et ibuprofen à leur
place. Le défaut appartient au jeu d'essai, pas à la récupération de l'application.

`jury-scenarios-initial.yaml` conserve le jeu utilisé et `http-acceptance.json`
conserve ses scores bruts, y compris ces deux FAIL. Les refus sont attendus sur le
fond pour des médicaments absents ; leurs scores ne sont pas réécrits en PASS.

Les deux questions de remplacement ont été définies depuis les fichiers réels,
avant leur exécution séparée : `eval/jury_coverage_replacements.yaml`.
Leurs résultats figurent dans `http-coverage-replacements.json`, sans les fusionner
avec la série initiale. Le jeu courant `eval/jury_scenarios.yaml` est corrigé pour
les prochaines campagnes. Un précontrôle et deux tests empêchent désormais un
fichier attendu absent d'être soumis au fournisseur par ce script.
