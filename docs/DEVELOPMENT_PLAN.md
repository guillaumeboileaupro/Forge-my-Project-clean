# Development Plan - Forge-my-Project

Reference: docs/SPECIFICATIONS.md. Valide: 14 novembre 2026. Les charges sont des estimations en journees de developpement, pas des dates de livraison.

## Phases
| Phase | Objectif | Charge | Sortie verifiable |
| --- | --- | ---: | --- |
| P1 | Stabiliser le prototype et preparer l'architecture | 2 j | Code actuel teste, architecture cible documentee |
| P2 | Formulaire hybride, questions conditionnelles et profils | 4 j | Parcours UI, stockage local et JSON fonctionnels |
| P3 | Regles, catalogues externes, generation documentaire | 6 j | AGENTS.md et documents coherents et personnalises |
| P4 | my-skills, recherche externe, packages et compatibilite | 5 j | Selection traçable, packages fictifs rejetes |
| P5 | Securite stricte, GitHub Actions, hooks, MCP optionnels | 6 j | Configurations generees verifiees, scans operationnels |
| P6 | Apercu, edition, diff, fusion et ecriture locale | 4 j | Aucune ecriture sans accord, sauvegardes testees |
| P7 | Tests, correction, documentation et recette finale | 3 j | DoD et recette finale satisfaites |
| **Total** | | **30 j** | |

## Dependances
P1 -> P2; P1 -> P3; P2 + P3 -> P4; P3 + P4 -> P5; P2 + P3 -> P6; P1-P6 -> P7. Les travaux sont executes progressivement avec une seule PR ouverte.

## Lots et mode de travail
Chaque phase peut etre divisee en plusieurs PR successives. Un seul agent developpeur a la fois. Pour chaque tache: implementation minimale, tests locaux, audit applicable, documentation et TODO a jour, PR unique, CI verte, revue, fusion et nettoyage. Ne jamais contourner les checks pour marquer DONE.

## Coordination des composants
T02 fixe les contrats de compatibilite dans docs/CONTRACTS.md et isole le prototype sous des modules `legacy`. Codex garde la couche UI et la gestion des fichiers: T16 valide l'apercu edite sans effet de bord; T17 ajoutera les operations locales confirmees. Claude developpe les catalogues, rules/planner, generation moderne, skills, verification et MCP. Toute substitution de la facade historique doit conserver les signatures et tests contractuels ou faire l'objet d'une decision documentee.

## Attention au perimetre
Le generateur ne produit PAS le code metier du projet cible. GitHub est source de skills et plateforme de CI des projets futurs, mais Forge-my-Project ne cree ni ne pousse de depot pour eux. Aucun LLM integre. Les MCP sont facultatifs.

## Risques a traiter tot
- Plans automatiques sans LLM: limiter aux modeles applicables, demander precision si informations insuffisantes.
- Auth GitHub: reuse Git/gh si disponible; jamais supposer la session VS Code transferée automatiquement.
- Contenu des skills distants: verifier et faire valider avant copie.
- Packages/API: verification difficile; garantir uniquement la portee effectivement controlee.
- Configs de securite et CI: tester les stacks officiellement supportees, sinon NON VERIFIE.
- Ecriture dans dossiers existants: path traversal, conflits, sauvegardes et rollbacks.

## Detail et charges
Voir TODO.md pour les 18 taches T01-T18 et les temps estimes, reels et ecarts. Le total de 30 j correspond aux taches retenues et doit etre reestime selon les integrations effectivement supportees.
