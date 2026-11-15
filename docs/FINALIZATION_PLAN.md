# Plan de finalisation - Forge-my-Project

Reference: docs/SPECIFICATIONS.md. Plan valide, implementation et preuves a completer progressivement.

## Definition de fini
L'outil local repond aux 40 choix confirmes, sans generation de code metier ni action GitHub distante sur un nouveau projet. Il prepare des fichiers exploitables, verifiables et adaptes, avec controles de securite stricts et consentement explicite avant ecriture.

## Gates obligatoires
Statut au 15 novembre 2026 : toutes PASS, preuves et reserves dans docs/ACCEPTANCE.md (G08 : MCP GitHub distant NON VERIFIE a l'execution).
- [x] G01 - Lancement local sur une machine propre, sans hebergement ni LLM.
- [x] G02 - Questionnaire hybride, choix conditionnels, profils et sauvegarde JSON fonctionnent.
- [x] G03 - Architecture/AGENTS.md/skills/docs/plans/TODO sont specifiques aux choix; commande inconnue signalee.
- [x] G04 - Regles communes et regles stack/agents correctement combinees; bibliotheque externe editable.
- [x] G05 - Selection my-skills par GitHub et validation des skills externes, sans execution arbitraire.
- [x] G06 - Controle packages, versions, APIs, licences et vulnérabilites avec preuve et etats explicites.
- [x] G07 - CI GitHub Actions, tests/couverture, audits et hooks fonctionnels sur les stacks annoncees.
- [x] G08 - MCP uniquement sur opt-in, serveurs reels, permissions minimales, pas de secrets.
- [x] G09 - Apercu, edition, comparaison, sauvegarde, fusion et ecriture dans dossier choisi testees.
- [x] G10 - Tests unitaires/integration/UI de Forge, CI verte, docs et rapport de generation complets.
- [x] G11 - Aucun bug bloquant ni vulnérabilite connue haute/critique non resolue; limitations non verifiees explicites.
- [x] G12 - Workflow Git strict documente; temps estime/reel/ecart mis a jour dans TODO.

## Recette
1. Lancer serveur, remplir et reprendre un questionnaire, importer/exporter une configuration.
2. Generer des fichiers pour au moins un profil Python et un profil JS/TS reellement supportes.
3. Verifier les contenus produits, commandes, docs, hooks, CI et skills.
4. Rejeter un faux package et un nom/chemin malicieux; simuler indisponibilite de registre -> NON VERIFIE.
5. Valider que les skills externes et MCP ne sont pas installes sans approbation.
6. Comparer deux versions d'un fichier, fusionner, sauvegarder, restaurer, puis ecrire dans un dossier existant.
7. Verifier l'absence de publication GitHub, de code metier et de requete vers un LLM.
8. Examiner logs et rapport sans secrets; executer tests du generateur et verifier CI.
9. Documenter les exceptions et le perimetre des stacks supportees, puis valider toutes les gates.

## Preuves
Pour chaque gate: PASS, FAIL ou NON VERIFIE, commandes, journaux/CI, date et responsable. NON VERIFIE n'est pas PASS. Une fonctionnalite hors support doit etre annoncee explicitement.
