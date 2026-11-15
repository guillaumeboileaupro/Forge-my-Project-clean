# Recette finale T18 - 15 novembre 2026

Responsable : Claude Code. Environnement : Linux (noyau 6.8, Ubuntu), Python 3.12.13 et 3.11 (CI), Node 24 (Volta), Firefox 158.0.1 headless via geckodriver, gh 2.4.0 authentifie, Gitleaks 8.30.1 (empreinte verifiee), Bandit 1.9.4.
Exigences et preuves detaillees : docs/TRACEABILITY.md. Statuts : PASS (execute et reussi), NON VERIFIE (non execute ou impossible a executer ici ; jamais compte comme PASS).

## Parcours complet sur installation propre
Commande : `python3 tests/acceptance_t18.py --clone <clone> --work <dossier hors du clone> --out rapport.json`, sur un `git clone` neuf de la branche livree (commit 7c0b29f), serveur demarre avec un HOME, une configuration et une racine d'ecriture vierges (seule la configuration `gh` existante est reutilisee, pour une recherche GitHub authentifiee ; le jeton n'est ni lu ni journalise). Le script refuse de demarrer si le port 8765 est deja utilise. Verifications en ligne reelles (npm, OSV, endoflife.date, registre MCP, GitHub). Resultat : **26 etapes, 26 PASS, 0 FAIL, 0 NON VERIFIE**.

| Etape | Resultat |
| --- | --- |
| 1 Demarrage sur installation propre | PASS : formulaire et 6 profils predefinis charges |
| 2-3 Description libre, profil `typescript-web-react` personnalise (agents Claude + Codex), architecture suggeree puis modifiee | PASS |
| 4 Technologies et dependances verifiees en ligne | PASS : 35 controles, 29 PASS, 6 NON VERIFIE (avertissements affiches et confirmes), 0 FAIL |
| 5 Recherche et approbation de skills (GitHub reel) | PASS : 10 candidats, `mcp-builder` approuve, reverification PASS |
| 6 MCP optionnels | PASS : GitHub (lecture seule) et Playwright |
| 7 Generation | PASS : 65 fichiers, skill approuve et configurations MCP presents |
| 8 Modification et validation | PASS : 2 fichiers modifies, 65 valides |
| 9 Dossier local existant (depot Git avec README) | PASS : 64 nouveaux, 1 conflit |
| 10 Comparaison, fusion manuelle du README, confirmation | PASS : 64 crees, 1 fusionne, contenu verifie sur disque |
| 11 Sauvegarde puis restauration manuelle documentee (docs/LOCAL_WRITE.md) | PASS : README sauvegarde, etat initial retrouve octet pour octet |
| 12 Tests et CI du projet ecrit (copie) : toutes les etapes `run` du workflow genere et hooks pre-commit / pre-push | PASS |
| R1-R10 Refus : configuration incompatible, nom malveillant, destinations dangereuses (hors racine, `..`, relative), lien symbolique, secret, `.mcp.json` elargi, modification concurrente (409, rien ecrit), package inconnu, version non supportee, verification reelle d'un package | PASS (10/10) |
| P1 / L1 Profils dans le HOME de recette ; journal serveur sans corps de requete ni secret | PASS |

## Qualite et securite
| Controle | Commande | Resultat |
| --- | --- | --- |
| Tests unitaires et d'integration | `python3 -m unittest discover -s tests` | PASS : 236 tests, 12 ignores (11 parcours Firefox sans FORGE_E2E, branche gitleaks sans outil) |
| Recette Firefox | `FORGE_E2E=1 python3 -m unittest tests.test_e2e_firefox` | PASS : 11/11 |
| Six profils generes, CI generee executee | `python3 tests/smoke_generated.py --verify` | PASS : 6/6 (python-api-fastapi, python-cli, python-library, python-web-django, typescript-api-express, typescript-web-react), hooks Git compris |
| Detection par les controles generes | `python3 tests/smoke_security.py` | PASS : secret (Gitleaks), injection shell (Bandit), dependance vulnerable (pip-audit, npm audit), `eval` (ESLint) detectes et bloquants |
| Secrets du depot | `gitleaks git .` (historique complet) | PASS : aucune fuite |
| SAST | `bandit -r forge server.py generator.py` (seuil CI medium) | PASS : 0 medium/high ; 3 low connues (`subprocess` pour gh, faux positif « PASS ») |
| Audit des dependances de Forge | - | Sans objet : bibliotheque standard uniquement, aucun manifeste ; les audits s'appliquent aux projets generes (ligne « Detection ») |
| Hooks generes | test_engine_hooks (hooks executes dans un vrai depot) + smoke | PASS |
| MCP Playwright genere | commande de `.mcp.json` lancee, `initialize` + `tools/list` en JSON-RPC stdio | PASS : protocole 2025-06-18, 25 outils |
| MCP GitHub distant | - | NON VERIFIE a l'execution : gh 2.4.0 n'offre pas `gh auth token` et le jeton n'a pas ete extrait des fichiers d'identification ; configuration (lecture seule, ensembles d'outils) et provenance (registre MCP officiel) verifiees |
| Absence de code metier | test_engine_documents.test_every_output_is_safe_documentation_without_business_code | PASS |
| CI GitHub de ce depot | jobs python, securite, CI generee des profils | voir la PR T18 |

## Plateformes
- Linux : PASS (toutes les lignes ci-dessus).
- macOS : NON VERIFIE (aucun environnement disponible). Le code n'utilise que des API POSIX presentes sur macOS (dir_fd, O_NOFOLLOW) ; a recetter avant d'annoncer le support.
- Windows : NON VERIFIE ; l'ecriture locale y est refusee par conception, le ZIP reste disponible.

## Anomalies trouvees et corrigees pendant la recette
1. Firefox 158 headless pilote par geckodriver interrompt parfois une seconde requete longue (NetworkError apres 20 a 65 s, reproduit avec un serveur minimal, non reproduit sur une requete isolee) : la recherche GitHub de skills (jusqu'a 45 s) echouait. Correction : une relance automatique unique des requetes sans effet de bord ; les ecritures ne sont jamais relancees. Preuve : test Firefox `test_interrupted_read_only_request_is_retried_once_but_writes_never` et une interruption reelle rattrapee pendant la recette (journal serveur).
2. Une source en ligne (skills my-skills) repondant differemment entre la verification et la validation provoquait un refus opaque « Liste de fichiers incoherente ». Correction : message explicite demandant de relancer la verification, avec les avertissements skills. Preuve : `test_changed_online_source_explains_the_file_set_mismatch`.
3. Documentation : README (portee, plateformes, configuration), AGENTS.md (pieges perimes : TypeScript limite au formulaire historique, lockfiles), LOCAL_WRITE.md (plateformes testees).

## Gates du plan de finalisation
| Gate | Statut | Preuve |
| --- | --- | --- |
| G01 Lancement local propre sans hebergement ni LLM | PASS | etape 1 |
| G02 Questionnaire, conditions, profils, JSON | PASS | T03/T04, Firefox, test_profiles |
| G03 Documents specifiques, commande inconnue signalee | PASS | test_engine_documents |
| G04 Regles communes + stack/agents, bibliotheque editable | PASS | test_engine_rules |
| G05 my-skills et skills externes sans execution | PASS | etape 5, test_engine_skills, test_engine_external_skills |
| G06 Packages, versions, API, licences, vulnerabilites | PASS | etape 4, R8-R10, test_engine_verification |
| G07 CI, tests, couverture, audits, hooks | PASS | smoke 6/6, smoke_security, etape 12 |
| G08 MCP opt-in, reels, minimaux, sans secret | PASS (GitHub distant NON VERIFIE a l'execution) | test_engine_mcp, MCP Playwright, R6 |
| G09 Apercu, edition, comparaison, sauvegarde, fusion, ecriture | PASS | etapes 7-11, test_filesystem_write |
| G10 Tests Forge, CI verte, docs, rapport | PASS | ce document, CI de la PR |
| G11 Aucun bug bloquant ni vulnerabilite haute/critique connue | PASS | Bandit, Gitleaks ; aucune anomalie ouverte |
| G12 Workflow Git strict, temps a jour | PASS | TODO.md, PR #14-#19 |

## Limitations restantes (non bloquantes, documentees)
- Fusion manuelle guidee par diff, sans fusion a trois voies ; fichiers binaires ou > 256 Kio : conserver ou remplacer.
- Pas de harnais E2E genere pour le projet cible (politique decrite dans TESTING.md).
- Protection de branche : commande fournie, a executer par le proprietaire (depot prive gratuit non protegeable).
- macOS et Windows non testes ; MCP GitHub distant non execute.
- Les « 40 choix confirmes » ne sont pas dans le depot (voir docs/TRACEABILITY.md).
