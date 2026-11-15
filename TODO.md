# TODO - Forge-my-Project

Reference: docs/SPECIFICATIONS.md et docs/DEVELOPMENT_PLAN.md.
Statuts: TODO, IN PROGRESS, BLOCKED, DONE. Les durees sont des estimations indicatives. Le temps reel et l'ecart restent a renseigner pendant le developpement.

## Cartographie
```text
T01 -> T02 -> T03 -> T04
        |      +-> T05
        +-> T06 -> T07 -> T08 -> T10 -> T14 -> T18
                        |      +-> T09 -> T10 -> T15 -> T18
                        |      +-> T11 -> T12 -> T13 -> T18
                        |      +-> T16 -> T17 -> T18
```
Le graphe est indicatif: la colonne Depend de fait foi.

## Taches
| ID | Phase | Travail | Depend de | Estime | Reel | Ecart | Statut | Critere de fin |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| T01 | P1 | Auditer le prototype et corriger ses defauts | - | 1 j | 0 h 05 | -7 h 55 (base 8 h/j) | DONE | Tests serveur/ZIP et JS reproductibles |
| T02 | P1 | Reorganiser modules et modeles externes sans casser l'existant | T01 | 1 j | 0 h 06 | -7 h 54 (base 8 h/j) | DONE | Contrats clairs, tests verts |
| T03 | P2 | Formulaire hybride, navigation et progression | T02 | 2 j | en cours | - | IN PROGRESS | Parcours UI valides |
| T04 | P2 | Questions conditionnelles et validation | T03 | 1 j | en cours | - | IN PROGRESS | Questions coherentes selon reponses |
| T05 | P2 | Profils, autosauvegarde et import/export JSON | T03 | 1 j | 0 h 09 | -7 h 51 (base 8 h/j) | DONE | Reprise et import fiable |
| T06 | P3 | Catalogue technologies et compatibilites | T02 | 2 j | 0 h 13 | -15 h 47 (base 8 h/j) | DONE | Configs incompatibles detectees |
| T07 | P3 | Moteur de regles et composition des templates | T06 | 2 j | 0 h 02 | -15 h 58 (base 8 h/j) | DONE | Rendu deterministe et coherent |
| T08 | P3 | AGENTS.md et documentation complete personnalisee | T07 | 2 j | 0 h 03 | -15 h 57 (base 8 h/j) | DONE | Aucun contenu fictif cache |
| T09 | P4 | Recuperer et selectionner les skills du depot my-skills | T07 | 1 j | 0 h 03 | -7 h 57 (base 8 h/j) | DONE | Skills pertinents copies sans execution |
| T10 | P4 | Recherche et validation de skills externes | T09 | 2 j | 0 h 14 | -15 h 46 (base 8 h/j) | DONE | Sources verifiees, accord utilisateur |
| T11 | P4 | Verifier packages, versions, compatibilites, API | T06 | 2 j | 0 h 03 | -15 h 57 (base 8 h/j) | DONE | Packages inconnus rejetes |
| T12 | P5 | GitHub Actions generees et verifiees | T07,T11 | 2 j | 0 h 16 | -15 h 44 (base 8 h/j) | DONE | Pipelines reels pour stacks supportees |
| T13 | P5 | Controles securite stricts et rapports | T11,T12 | 2 j | 0 h 12 | -15 h 48 (base 8 h/j) | DONE | Scans applicables et blocage fiable |
| T14 | P5 | Hooks Git et agents suivant leurs capacites | T07 | 1 j | 0 h 11 | -7 h 49 (base 8 h/j) | DONE | Hooks activables et executes |
| T15 | P5 | MCP optionnels verifies et valides | T10 | 1 j | 0 h 12 | -7 h 48 (base 8 h/j) | DONE | Aucun MCP fictif ni secret |
| T16 | P6 | Explorateur, apercu et edition des fichiers | T08 | 2 j | 0 h 15 | -15 h 45 (base 8 h/j) | DONE | Modifications visibles avant ecriture |
| T17 | P6 | Diff, fusion assistee, sauvegarde, ecriture locale | T16 | 2 j | 0 h 12 | -15 h 48 (base 8 h/j) | DONE | Conflits et rollback testes |
| T18 | P7 | Tests finaux, corrections, docs et rapport | T01-T17 | 3 j | - | - | TODO | Critères de finalisation valides |
| **Total** | | | | **30 j** | **-** | **-** | | |

## Ordre de travail
Commencer par T01. Une seule PR ouverte et un seul agent de developpement a la fois. Actualiser les colonnes Reel/Ecart apres chaque tache et noter les preuves CI dans la PR.

## Etat existant
Le serveur local, le formulaire initial, le ZIP, AGENTS.md, une bibliotheque initiale de skills, des docs et une CI du depot existent. Les fonctions cible non implementees ne doivent pas etre marquees DONE.

## Notes de suivi
Pour chaque tache terminee: commande et resultat des tests, lien du run CI, impact securite, fichiers modifies, temps reel, blocages et risque residuel. Aucune tache DONE sans preuve.

### T01 - 14 novembre 2026
- Temps reel mesure: 0 h 05, de la creation de la branche dediee a la premiere CI de PR verte.
- Tests: `python3 -m unittest discover -s tests -v` PASS, 20 tests; `python3 -m compileall -q generator.py server.py tests` PASS.
- Archives: 64 combinaisons supportees controlees, chemins ZIP bornes a la racine, tests generes Python et `npm test` executes avec succes.
- Serveur et formulaire: integration HTTP loopback PASS; rendu Firefox headless PASS; contrat des champs et options PASS.
- Securite: validation stricte des champs, de `Host` et du type JSON; en-tetes navigateur durcis; recherche ciblee de secrets sans correspondance.
- CI: [push PASS](https://github.com/guillaumeboileaupro/Forge-my-Project/actions/runs/43583433146) et [PR PASS](https://github.com/guillaumeboileaupro/Forge-my-Project/actions/runs/43583453284).
- NON VERIFIE: Bandit, Semgrep et Gitleaks absents. `pip check` signale des incoherences de l'environnement Anaconda global, sans dependance tierce du projet.
- Risques restants hors T01: profil nomme TypeScript mais base JavaScript, workflow genere volontairement bloquant, absence de lockfiles et fonctions T02-T18 non implementees.

### T02 - 14 novembre 2026 (Codex, PR #5)
- Temps reel mesure: 0 h 06, de la creation de la branche dediee a la premiere CI push verte.
- Tests locaux: 24 tests PASS; compilation Python PASS; 64 configurations avec sorties `build()` octet pour octet identiques a T01; projets generes Python et JavaScript executes avec succes.
- Recette: serveur HTTP local PASS; formulaire et assets externes rendus dans Firefox headless PASS; regression du checkbox sous CSP detectee puis corrigee avant livraison.
- Securite: templates rendus en un passage, traversee `..` refusee, assets servis par liste fermee et CSP sans `unsafe-inline`.
- CI et integration: [push PASS](https://github.com/guillaumeboileaupro/Forge-my-Project/actions/runs/43584707105), [PR PASS](https://github.com/guillaumeboileaupro/Forge-my-Project/actions/runs/43584848078), fusion `6506dd0` dans `main`.

### T06-T11 - 14 novembre 2026 (Claude Code, PR #6)
- Temps reels mesures sur l'historique Git: branche creee a 10 h 54; commits T06 11 h 07, T07 11 h 09, T08 11 h 12, T11 11 h 15, T09 11 h 18, T10 11 h 21; fusion 11 h 28 (total 0 h 34).
- Tests: `python3 -m unittest discover -s tests` PASS, 90 tests apres synchronisation avec T02; pyflakes sans alerte.
- CI: [push PASS](https://github.com/guillaumeboileaupro/Forge-my-Project/actions/runs/43585339901) et [PR PASS](https://github.com/guillaumeboileaupro/Forge-my-Project/actions/runs/43585342252) (Python 3.11).
- Verifications reelles: package fictif rejete; django 3.0.0 et lodash 4.17.15 bloques (GHSA haute/critique); Node 20 et Python 3.9 bloques (fin de vie); 6 skills my-skills copies au commit 16cddc53, scripts ignores.
- T10 reste IN PROGRESS: recherche et approbation disponibles dans le moteur et la CLI, pas encore dans l'interface.
- NON VERIFIE: API des packages (pas d'installation); licence PyPI = derniere version publiee.

### Integration moteur/formulaire - 14 novembre 2026 (Claude Code, PR #8)
- Formulaire hybride sur `/`, API locale `/api/catalog|plan|archive`, formulaire historique sur `/legacy`; recette Firefox headless en CI.
- Temps reel: 11 h 28 (fusion PR #6) -> 11 h 35 (CI verte), fusion par l'utilisateur a 11 h 43.
- T03/T04 restent IN PROGRESS: la liste des 40 choix valides n'est pas dans le depot, couverture complete non verifiable.

### T05 - 14 novembre 2026 (Claude Code)
- Temps reel: 11 h 44 -> 11 h 53 (0 h 09) jusqu'a la PR; CI et fusion notees dans la PR.
- Profils predefinis (6, chacun genere un plan valide), profils personnels CRUD dans un fichier local 0600 a ecriture atomique, sauvegarde automatique (`localStorage`, ecriture immediate a la fermeture) revalidee avant restauration, import/export JSON valide par le serveur.
- Tests: unitaires et HTTP (`tests/test_profiles.py`), recette Firefox (`FORGE_E2E=1`): restauration des choix conditionnels, brouillon incompatible ignore, cycle de vie des profils, export puis import, JSON invalide et configuration incompatible refuses. Recette executee 3 fois de suite sans echec.
- Defaut corrige pendant la recette: une modification suivie d'un rechargement en moins de 300 ms etait perdue; sauvegarde forcee sur `pagehide`.
- Limites: les approbations de skills externes importees ne sont pas conservees par l'interface (avertissement affiche); le brouillon est propre au navigateur.

### T12 - 14 novembre 2026 (Claude Code)
- Temps reel: 11 h 57 -> 12 h 13 (0 h 16) jusqu'a la PR; CI et fusion notees dans la PR.
- CI generee par le moteur: actions officielles epinglees par SHA (checkout v7.0.1, setup-python v7.1.0, setup-node v7.1.0, verifiees via l'API GitHub), permissions en lecture, une etape par commande du catalogue, seuil de couverture 80 %; manifestes et configurations d'outils minimaux sans code metier.
- Preuve: `tests/smoke_generated.py --verify` execute la CI generee des 6 profils predefinis: PASS localement (Python 3.12, Node 24) et dans le job `generated-projects`.
- Defaut reel detecte et corrige: typescript-eslint 8.72.2 n'accepte pas TypeScript 7 (ERESOLVE). Ajout de la resolution des peerDependencies npm (T11): TypeScript ajuste a 6.0.3 avec trace.
- NON VERIFIE: pas de lockfile genere; Django sans squelette manage.py; seuils de couverture appliques a un code vide (100 %) jusqu'aux premiers modules.

### T13 - 14 novembre 2026 (Claude Code)
- Temps reel: 12 h 19 -> 12 h 31 (0 h 12) jusqu'a la PR; CI et fusion notees dans la PR.
- Outils verifies sur leurs sources officielles le 14 novembre 2026: Gitleaks 8.30.1 (empreinte SHA-256 identique dans le fichier de sommes publie et le digest GitHub), Bandit 1.9.4, pip-audit 2.10.1, cyclonedx-bom 8.0.1 (PyPI), eslint-plugin-security 4.2.1 (npm), actions/upload-artifact v7.0.2 (SHA via l'API GitHub).
- Preuves: `tests/smoke_security.py` (secret, injection shell, urllib3 1.24.1, lodash 4.17.15, eval) -> chaque controle echoue comme attendu, temoins PASS; `tests/smoke_generated.py --verify` -> 6/6 profils PASS sur les jobs quality et security.
- Ce depot: Gitleaks (historique) et Bandit sans alerte; jobs CI `security` et preuve de detection ajoutes.
- Limites: pip-audit ne filtre pas par severite (toute vulnerabilite connue bloque); pas de scanner d'image conteneur (NON VERIFIE); Semgrep non retenu (regles telechargees a l'execution), SAST JS limite a eslint-plugin-security.

### T13 - suivi
- PR #11 fusionnee le 14 novembre 2026 a 12 h 40 apres CI verte (6 jobs, dont generated-projects : 6/6 profils et 5/5 problemes injectes detectes sur les runners GitHub).

### T14 - 14 novembre 2026 (Claude Code)
- Temps reel: 12 h 40 -> 12 h 51 (0 h 11) jusqu'a la PR; CI et fusion notees dans la PR.
- Capacites des agents verifiees dans leur documentation officielle: Claude Code (hooks PreToolUse, code 2 bloquant), Codex (learn.chatgpt.com/docs/hooks et source openai/codex: `.codex/hooks.json`, PreToolUse sur Bash/apply_patch, code 2 + stderr, revue `/hooks` requise), GitHub Copilot (docs.github.com hooks-configuration: `.github/hooks/*.json`, version 1, preToolUse, code 2 = refus, fail-closed).
- Tests: `tests/test_engine_hooks.py` (garde-fou sur les 3 formats d'evenements, configurations, droits 0755, commits reels: message non conforme, `.env` force, motif de secret, outil absent, pre-push tests OK/KO, branche gitleaks); `tests/smoke_generated.py`: hooks pre-commit et pre-push generes executes avec les outils reels, 6/6 profils PASS.
- Defaut detecte et corrige: le garde-fou genere ne respectait pas `ruff format`/`ruff check` du projet cible.
- Limites: le garde-fou exige Python 3 (y compris pour les projets Node); detection par motifs (pas d'analyse complete du shell); les hooks Codex doivent etre approuves via `/hooks`; activation des hooks Git manuelle (`core.hooksPath`), aucun hook n'est installe automatiquement.

### T10 - 15 novembre 2026 (Claude Code)
- Temps reel: 0 h 03 (moteur et CLI, PR #6) + 11 h 23 -> 11 h 34 (0 h 11) pour l'integration au formulaire et l'integrite des approbations, jusqu'a la PR; CI et fusion notees dans la PR.
- Formulaire: section « Skills externes » (recherche explicite, fiche nom/description/provenance/commit/empreinte/fichiers copies et ignores, Approuver/Refuser, confirmation pour une source non reconnue, verification en ligne PASS/FAIL/NON VERIFIE). API `POST /api/skills/search` et `POST /api/skills/verify`.
- Integrite: approbation = depot + commit + empreinte SHA-256 de l'arborescence complete du skill; skill modifie depuis l'approbation ou contenu telecharge different du blob = erreur bloquante `skill-modified`. Approbations sans empreinte refusees a l'import avec un message explicite; un meme nom de skill ne peut etre approuve qu'une fois.
- Conservation: approbations dans le brouillon, les profils et l'export/import JSON, revalidees par le serveur.
- Tests: `tests/test_engine_external_skills.py` (empreinte, contenu modifie/ajoute/script modifie, telechargement falsifie, verification), `tests/test_skills_api.py` (5 tests HTTP: recherche, refus, verification, export/import/profil, generation bloquee), recette Firefox `test_external_skills_approval` (recherche, approbation, refus, rechargement, verification PASS puis FAIL, generation bloquee puis debloquee). 181 tests unitaires OK (7 ignores sans FORGE_E2E), recette Firefox 6/6.
- Verification reelle (GitHub, `gh` et HTTPS anonyme): 8 candidats pour un projet web React; copie de `webapp-testing` avec controle des blobs OK, scripts `examples/*.py` ignores; empreinte falsifiee = FAIL.
- Defaut corrige: la barre laterale fixe depassait la hauteur de fenetre (bouton Reinitialiser inaccessible); elle defile desormais.
- Limites: refus conserves uniquement pendant la session; l'empreinte repose sur les SHA-1 de blobs Git fournis par GitHub; la recherche de code GitHub exige la CLI gh authentifiee; la decision de confiance reste humaine.

### T15 - 15 novembre 2026 (Claude Code)
- Temps reel: 11 h 35 -> 11 h 47 (0 h 12), recherche documentaire pendant la CI de T10 puis branche dediee apres fusion de T10; CI et fusion notees dans la PR.
- Catalogue `catalogs/mcp/servers.json` verifie a la source: registre MCP officiel (`io.github.github/github-mcp-server` 2.1.0, `io.github.microsoft/playwright-mcp` 0.0.85, statut actif), depots GitHub actifs, licences MIT et Apache-2.0, npm `@playwright/mcp` 0.0.85.
- Formats d'agents verifies dans la documentation officielle: `.mcp.json` (Claude Code; destination native de Copilot dans VS Code, `${VAR}` dans les en-tetes), `.codex/config.toml` (`bearer_token_env_var`, `http_headers`, projets approuves uniquement).
- Section « Skills et MCP » du formulaire: serveurs pertinents seulement, aucun coche par defaut, provenance, permissions et variable du jeton affichees; selection retiree si le type de projet la rend non pertinente.
- Tests: `tests/test_engine_mcp.py` (11: catalogue strict, aucune sortie sans selection, fichiers par agent, JSON/TOML relus, absence de secret, pertinence, registre PASS/FAIL/NON VERIFIE, provenance fausse bloquante), API `test_mcp_servers_are_opt_in_and_revalidated`, recette Firefox `test_mcp_selection`. 194 tests unitaires OK (8 ignores: 7 parcours Firefox sans FORGE_E2E, branche gitleaks sans outil), recette Firefox 7/7.
- Verification reelle: registre MCP, npm et OSV PASS pour les deux serveurs; Gitleaks 8.30.1 (empreinte verifiee) sur un projet genere avec MCP: aucune fuite; Bandit: aucune alerte.
- Limites: deux serveurs au catalogue; l'agent cloud Copilot se configure dans les parametres du depot; le serveur GitHub distant exige un jeton fourni par l'utilisateur; Playwright MCP n'est pas une frontiere de securite (documentation officielle); la phrase Codex sur le chargement reserve aux projets approuves provient de la page MCP (« trusted projects only »).

### T16 - 15 novembre 2026 (Codex)
- Temps reel mesure: 0 h 06, de la creation du worktree a la premiere recette Firefox complete verte.
- Interface: explorateur hierarchique, navigation precedent/suivant, apercu editable, marqueur par fichier, compteur global et restauration du contenu genere.
- Validation: `POST /api/files/validate` regenere le plan et exige l'ensemble exact des chemins; l'archive repete ce controle et contient les editions validees.
- Securite: ajout/suppression/traversee de chemin, texte non UTF-8 ou avec NUL, fichier > 256 Kio et ensemble > 2 Mio refuses; aucune ecriture locale dans T16.
- Tests locaux: 187 PASS, 7 ignores dans la suite standard; compilation Python et `node --check` PASS; recette Firefox headless 6/6 PASS.
- T17 reste a faire: destination, diff, fusion, sauvegarde, confirmation, ecriture et rollback.

### T16 - reprise et integration - 15 novembre 2026 (Claude Code, PR #15)
- Codex indisponible: reprise de la branche `codex/file-preview` depuis un worktree independant (worktree personnel de Codex non modifie), fusion de `origin/main` (T10, T15) sans reecriture d'historique ni push force.
- Temps reel de la reprise: 13 h 06 -> 13 h 15 (0 h 09), en plus des 0 h 06 de Codex; total T16 0 h 15.
- Conflits resolus en conservant les deux apports: `forge/web.py` (validation de l'apercu + `_mcp_payload`), `ui/js/app.js` (invalidation de l'apercu + `updateMcp`), `docs/CONTRACTS.md`, `AGENTS.md`, `README.md`, `TODO.md`.
- Correction d'interaction: approuver ou retirer un skill invalide desormais l'apercu valide (`approvalsChanged` appelait seulement `disabled`, la validation restait acquise); recette MCP adaptee au parcours valider-puis-telecharger.
- Tests ajoutes: API `tests/test_skills_api.py` (skill approuve et MCP edites presents dans le ZIP, scripts jamais copies; editions refusees si MCP, approbations ou agents changent; skill modifie bloquant meme avec editions; injection de `.mcp.json`, `.codex/config.toml` ou d'un skill non approuve refusee), `test_preview_routes_never_write_to_disk` (apercu, validation et archive sans aucune ouverture en ecriture), Firefox `test_editor_and_skill_approval_interact` et extension de `test_mcp_selection` (archive capturee dans la page, sans ecriture du telechargement par Firefox, contenant l'edition).
- Resultats locaux: 205 tests OK (9 ignores: 8 parcours Firefox sans FORGE_E2E, branche gitleaks sans outil); recette Firefox headless 8/8; compilation Python et `node --check` PASS; CI generee des six profils predefinis PASS 6/6 en local avec `--verify` (python-api-fastapi, python-cli, python-library, python-web-django, typescript-api-express, typescript-web-react; Gitleaks inclus).
- Securite: Bandit 1.9.4 aucune alerte au seuil CI (3 LOW preexistantes, identiques a `main`); Gitleaks 8.30.1 sur l'historique de la branche et sur forge/ui/tests: aucune fuite; seules ecritures du code applicatif: magasin de profils (`forge/config/profiles.py`), aucune dans un projet cible.
- CI: premier run push en echec sur `test_engine_hooks` (T14, course `maintenance.lock` entre la maintenance Git detachee et la suppression du depot temporaire, sans lien avec T16); correction: `gc.auto=0` et `maintenance.auto=false` dans le depot de test.
- Limites: le contenu edite n'est pas rescanne pour les secrets avant l'archive (la CI generee lance Gitleaks); une edition de `.mcp.json` ou d'un skill n'est pas revalidee semantiquement (seuls chemins, encodage et tailles); les editions sont perdues si la configuration change.

### T17 - 15 novembre 2026 (Claude Code, a la place de Codex indisponible)
- Temps reel: 13 h 33 -> 13 h 45 (0 h 12), de la synchronisation de `main` a la recette Firefox complete verte; CI et fusion notees dans la PR.
- Destination: saisie ou parcours des sous-dossiers de la racine autorisee (`FORGE_WRITE_ROOT`, sinon dossier personnel), dossier nouveau ou existant, droits verifies; chemins relatifs, `..`, racine, dossier de Forge-my-Project et liens symboliques refuses (parcours par descripteurs O_NOFOLLOW).
- Comparaison: nouveau, identique, conflit (diff unifie), bloque (lien, fichier special); decision obligatoire pour chaque conflit (conserver, remplacer, fusion manuelle); aucune ecriture pendant la comparaison.
- Ecriture: confirmation explicite, jeton HMAC de validation (etat des cibles, contenus, destination), reverification de chaque cible, sauvegarde `.forge-backup/<horodatage>/` avec MANIFEST.json, ecriture atomique (temporaire, fsync, rename), rollback automatique, rapport final (operations, sauvegarde, avertissements).
- Limites T16 corrigees: contenu edite et fusionne controle a la validation, a l'archive et a l'ecriture (secrets, `.mcp.json`/`.codex/config.toml`/hooks d'agents figes hors mise en forme, scripts de hooks non modifiables, nom de skill conserve, chemins sensibles interdits); validation perimee bloquee cote interface et serveur.
- Tests: `tests/test_filesystem_write.py` (21: destinations dangereuses, liens symboliques sur le chemin, la cible et un sous-dossier, FIFO, dossier nouveau/existant, identique/different, conserver/remplacer/fusionner, refus d'ecrasement sans decision, confirmation, modification concurrente avant et pendant l'ecriture, echec d'ecriture avec restauration et suppression des dossiers crees, secrets, MCP/hooks/skills, chemins sensibles), API (parcours compare/confirm/409/sauvegarde, secret bloque sur validate/archive/compare), skills et MCP approuves ecrits a l'identique et skill modifie bloquant, recette Firefox `test_local_write_journey`.
- Resultats locaux: 230 tests OK (10 ignores: 9 parcours Firefox sans FORGE_E2E, branche gitleaks sans outil); recette Firefox headless 9/9; compilation Python et `node --check` PASS; Bandit 1.9.4 aucune alerte au seuil CI; Gitleaks 8.30.1 aucune fuite.
- Documentation: docs/LOCAL_WRITE.md (parcours, garanties, sauvegarde, restauration manuelle), CONTRACTS, SECURITY, ARCHITECTURE, README, AGENTS.
- Limites: Linux et macOS uniquement (ZIP ailleurs); fusion manuelle sans fusion a trois voies; fichier existant binaire ou > 256 Kio: conserver ou remplacer; configurations MCP/hooks existantes non fusionnables; detection de secrets par motifs (Gitleaks reste la reference); `.forge-backup/` a exclure du depot par l'utilisateur; jeton invalide apres redemarrage du serveur.

