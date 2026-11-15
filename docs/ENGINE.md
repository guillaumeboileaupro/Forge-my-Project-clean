# Moteur technique (forge/)

Taches T06-T11. Bibliotheque standard Python 3.11+, aucun modele d'IA, aucune generation de code metier, aucune ecriture disque : le moteur produit un apercu `{chemin: contenu}` que l'interface (T16/T17) affiche, fait modifier et ecrit apres validation.

## Point d'entree

```python
from forge.pipeline import run

result = run(config, verify=False, skills=False)  # aucune requete reseau
result.files        # {chemin relatif: contenu}
result.diagnostics  # Diagnostic(code, severity error|warning|info, message, subject)
result.as_dict()    # rapport JSON (ok, regles, fichiers, diagnostics, verification, skills)
```

- `verify=True` : verification en ligne des packages, versions, vulnerabilites et runtimes (T11).
- `skills=True` : recuperation des skills my-skills et des skills externes approuves (T09/T10).
- Une erreur bloquante leve `forge.diagnostics.ForgeError` avec ses diagnostics.
- Recherche de skills externes (candidats, aucune copie) : `forge.skills.service.search_for_plan(plan)` ; controle d'approbations sans copie : `forge.skills.service.verify_approvals(approvals)`.

CLI equivalente (apercu uniquement) :

```bash
python -m forge plan spec.json [--verify] [--skills]
python -m forge show spec.json AGENTS.md
python -m forge skills-search spec.json
```

## Configuration d'entree (schema_version 1)

| Champ | Type | Regle |
| --- | --- | --- |
| name | texte | 3-50 caracteres, minuscules, chiffres, tirets |
| description | texte | 2000 caracteres max, optionnel (sinon avertissement) |
| project_type | choix | library, cli, api, web |
| technologies | liste | identifiants du catalogue (au moins une) |
| versions | objet | id -> version (`"3.12"`), sinon version preferee du catalogue |
| agents | liste | codex, claude, copilot (au moins un) |
| security | choix | strict (defaut), hardened |
| architecture | texte | 4000 caracteres max ; prioritaire sur la suggestion |
| options | objet | `{"mcp": bool}` derive de `mcp_servers` (true sans serveur choisi = refuse) |
| mcp_servers | liste | identifiants de `catalogs/mcp/servers.json`, pertinents pour le type de projet (10 au plus) ; vide = aucun fichier MCP |
| external_skills | liste | approbations `{repository, commit (SHA complet), path, name, digest (sha256:...)}` ; un nom de skill au plus une fois |

Les textes libres sont des donnees : jamais reinterpretes comme modele ni commande.

## Donnees externes (editables, validees avant usage)

- `catalogs/technologies/` : categories (bornes min/max, commandes requises) et technologies (`requires`, alternatives `[[a, b]]`, `conflicts`, `constraints` de version, `commands`, package du registre, versions supportees, documentation officielle https).
- `catalogs/rules/` : regles declaratives. `base` est obligatoire ; les autres s'appliquent selon `when` (`technologies_all/any`, `agents_any`, `project_types`, `security`, `options`). Elles ajoutent des fichiers (template -> chemin), des phrases par section et des skills recommandes. Ordre deterministe (priorite, id) ; deux regles produisant le meme fichier sans `override` = erreur.
- `templates/` : modeles de documents (`{{ var }}`, `{{#if}}`, `{{#each}}`, `{{else}}`, `{{! commentaire }}`) ; aucune evaluation de code, variable inconnue = erreur.
- `catalogs/skills/sources.json` : depot my-skills, catalogues externes reconnus, politique de copie.
- `catalogs/mcp/servers.json` : serveurs MCP proposes (nom du registre MCP officiel, depot, licence, pertinence, transport, permissions) ; valide strictement (HTTPS, aucun en-tete Authorization, commande `npx`/`uvx`, package epingle egal a la version executee).

Ajouter une technologie : une entree JSON dans le bon fichier de categorie, puis `python3 -m unittest discover -s tests`.

## Etats et blocages

| Situation | Resultat |
| --- | --- |
| Technologie inconnue, dependance manquante, conflit, version non supportee ou hors contrainte | erreur bloquante |
| Package inexistant, version absente/retiree, vulnerabilite haute ou critique, runtime en fin de vie | erreur bloquante (avec `verify`) |
| Registre ou service injoignable, severite inconnue, API d'un package | NON VERIFIE (avertissement), jamais PASS |
| Commande de test inconnue, description vide, architecture non definie | avertissement ; rendu `NON DEFINI` |
| Skill absent, rejete, indisponible ou contenant une commande a risque | avertissement |
| Skill modifie depuis son approbation, ou contenu telecharge different du blob du commit | erreur (`skill-modified`) |
| Skills externes approuves sans recuperation des skills demandee | avertissement (`skills-not-fetched`) |

## Reseau

Uniquement sur demande (`verify`, `skills`, `skills-search`), en HTTPS vers une liste fermee : pypi.org, registry.npmjs.org, api.osv.dev, endoflife.date, api.github.com, raw.githubusercontent.com, registry.modelcontextprotocol.io (redirections controlees). Pour GitHub, la CLI `gh` authentifiee est reutilisee si presente (le jeton reste gere par gh), sinon acces anonyme aux depots publics.

## Skills

- Selection : skills recommandes par les regles appliquees.
- Lecture a un commit epingle ; copie des seuls fichiers texte (.md, .yaml, .yml, .json, .txt) dans `.agents/skills/` (Codex) et `.claude/skills/` (Claude Code). Scripts, executables, liens et binaires ne sont jamais telecharges et sont listes dans `docs/SKILLS.md`.
- Skills externes : candidats de catalogues reconnus (et recherche GitHub si gh est authentifie, marques « source non reconnue ») ; copie uniquement apres approbation explicite enregistree dans `external_skills`, au commit approuve.
- Integrite (T10) : l'approbation porte l'empreinte `digest` = SHA-256 des lignes `mode sha-du-blob chemin` de **tous** les fichiers du dossier du skill au commit approuve (scripts compris). A la copie et a la verification, l'empreinte est recalculee : tout ajout, suppression ou modification de fichier refuse le skill (erreur bloquante, nouvel examen et nouvelle approbation necessaires). Chaque fichier telecharge est en outre compare au SHA de son blob Git. Une approbation sans empreinte (format anterieur) est refusee a l'import avec un message explicite.
- Interface : section « Skills externes » du formulaire (recherche explicite, fiche par candidat avec nom, description, provenance, commit, empreinte, fichiers copies et ignores, lien d'examen sur GitHub, boutons Approuver / Refuser ; confirmation supplementaire pour une source non reconnue). Les approbations suivent les reponses : brouillon, profils, export/import JSON ; « Verifier les approbations » les controle en ligne (PASS / FAIL / NON VERIFIE). Les refus ne sont conserves que pendant la session : seul ce qui est approuve entre dans la configuration.

## Fichiers de pile et CI generee (T12)

- Regles `scaffold-*` : `pyproject.toml` (extras `dev`, pytest, couverture, Ruff, mypy strict), `package.json` (scripts, `engines`), `tsconfig.json` strict, `eslint.config.js`, `vitest.config.js` (seuils), `.gitignore`, package vide `src/{package}/__init__.py` ou `src/index.(js|ts)` et un test de fumee. Aucun code metier.
- `.github/workflows/ci.yml` : actions officielles epinglees par SHA complet (`catalogs/ci/actions.json`), `permissions: contents: read`, `persist-credentials: false`, une etape par commande du catalogue (installation, formatage, lint, typage, tests avec seuil de couverture 80 %, audit, build). Le deploiement n'est jamais execute.
- Versions : sans verification, manifestes non contraints (`latest` pour npm) et dependances NON VERIFIE ; avec `verify`, versions verifiees (`>=` PyPI, `^` npm).
- Compatibilite npm : les `peerDependencies` entre packages retenus sont resolues (versions stables les plus recentes compatibles, ex. TypeScript abaisse si typescript-eslint ne le supporte pas) ; impossible = FAIL bloquant, plage illisible = NON VERIFIE.
- Actions : avec `verify`, chaque tag est relu sur l'API GitHub ; un tag deplace = FAIL bloquant.
- Preuve : `python3 tests/smoke_generated.py --verify` genere chaque profil predefini dans un dossier temporaire et execute toutes les etapes du workflow genere (job CI `generated-projects`).

## Securite stricte des projets generes (T13)

- Job CI `security` genere pour chaque projet : Gitleaks (binaire de release epingle, empreinte SHA-256 controlee par `sha256sum --check`, historique Git complet), Bandit (Python, severite >= medium en strict, >= low en hardened), pip-audit (toute vulnerabilite connue), `npm audit` (>= high en strict, >= moderate en hardened), SBOM CycloneDX (cyclonedx-bom pour Python, `npm sbom` pour npm) publiees en artefact.
- SAST JavaScript/TypeScript : eslint-plugin-security dans le lint (`--max-warnings 0`, job quality). Sans ESLint, ou pour une image Docker : diagnostic NON VERIFIE et ligne NON VERIFIE dans SECURITY.md.
- Outils dans un environnement isole, versions epinglees dans `catalogs/security/tools.json` ; avec `verify`, versions PyPI (+ OSV) et empreinte Gitleaks (digest de la release GitHub) sont recontrolees, une divergence bloque.
- Aucun contournement genere (`continue-on-error`, `|| true`...) ; les exceptions sont explicites et documentees dans SECURITY.md.
- Preuve de detection : `python3 tests/smoke_security.py` injecte un secret, une injection shell, une dependance Python vulnerable, une dependance npm vulnerable et un `eval` ; chaque controle doit echouer, le temoin doit passer (job CI `generated-projects`).

## Hooks Git et hooks d'agents (T14)

- Hooks Git (`.githooks/`, activation `git config core.hooksPath .githooks`, archive en 0755) sans redondance : pre-commit = secrets des fichiers indexes (gitleaks si installe, sinon controle reduit annonce NON VERIFIE), formatage, lint ; commit-msg = Conventional Commits ; pre-push = typage et tests. Audits, SBOM et historique complet restent dans la CI. Un outil absent fait echouer le hook avec une explication (aucun saut silencieux).
- Garde-fou PreToolUse commun (`scripts/hooks/agent_guard.py`, Python 3) : refuse `--no-verify`, `commit -n`, push force, modification de `core.hooksPath`, ecriture de `.env` (sauf `.env.example`) et de cles privees ; code 2 + raison sur stderr ; entree illisible refusee.
- Branchement selon les capacites documentees de chaque agent (verifiees le 14 novembre 2026) : Claude Code `.claude/settings.json` (`PreToolUse`) ; Codex `.codex/hooks.json` (`PreToolUse`, matcher `Bash|apply_patch`, hooks de projet actifs seulement apres revue `/hooks` et projet approuve) ; GitHub Copilot `.github/hooks/forge-guard.json` (`version: 1`, `preToolUse`, Copilot CLI et agent cloud, fichier requis sur la branche par defaut pour l'agent cloud). Aucun autre evenement n'est genere.
- Preuves : tests fonctionnels sur de vrais depots Git (`tests/test_engine_hooks.py`) et execution des hooks generes avec les outils reels pour chaque profil (`tests/smoke_generated.py`).

## Serveurs MCP optionnels (T15)
- Aucun fichier MCP sans selection explicite dans `mcp_servers`. Seuls les serveurs pertinents sont proposes (GitHub pour tout projet, le workflow genere reposant sur GitHub ; Playwright pour les projets web) ; un serveur inconnu ou non pertinent est une erreur bloquante.
- Fichiers generes selon les agents : `.mcp.json` (objet `mcpServers`) pour Claude Code et GitHub Copilot dans VS Code (destination native partagee), `.codex/config.toml` (`[mcp_servers.<id>]`) pour Codex, et `docs/MCP.md` (besoin, provenance, licence, statut, permissions, activation par agent). Formats verifies le 2026-11-15 dans la documentation officielle (code.claude.com, learn.chatgpt.com, code.visualstudio.com).
- Aucun secret : le jeton GitHub est reference par `${GITHUB_PERSONAL_ACCESS_TOKEN}` (`.mcp.json`) ou `bearer_token_env_var` (Codex). Controle Gitleaks 8.30.1 sur un projet genere avec MCP : aucune fuite.
- Permissions minimales : GitHub en lecture seule (`X-MCP-Readonly: true`) et limite aux ensembles `repos,issues,pull_requests,actions` ; Playwright epingle (`@playwright/mcp@0.0.85`), profil en memoire (`--isolated`), sans interface (`--headless`), sans acces fichiers hors espace de travail.
- Verification en ligne (`verify`) : registre MCP officiel (`/v0/servers/<nom>/versions/latest` : actif, depot et transport concordants), npm et OSV pour le package epingle ; FAIL bloque la generation, sans verification le statut reste NON VERIFIE (avertissement `mcp-unverified`). Node.js absent du projet pour Playwright : avertissement `mcp-runtime`.
- Activation : chaque agent demande une approbation (Claude Code : serveurs de projet en attente jusqu'a approbation ; VS Code : Workspace Trust ; Codex : projet approuve). L'agent cloud Copilot se configure dans les parametres du depot, pas par fichier.

## Limites connues

- Les API des packages ne sont pas verifiees automatiquement (etat NON VERIFIE explicite).
- La licence PyPI est celle de la derniere version publiee.
- La recherche de skills externes lit chaque SKILL.md des catalogues reconnus : plusieurs dizaines de secondes.
- Le catalogue couvre Python et Node.js/TypeScript ; toute autre pile est refusee comme inconnue.
- Pas de lockfile genere (il exige d'executer l'installateur) : la CI generee utilise `npm install` tant que `package-lock.json` n'est pas versionne, puis `npm ci`.
- Django : pas de squelette `manage.py` genere ; les tests passent par pytest.
- Le moteur est branche sur le formulaire hybride (`/`, API `/api/*`, voir docs/CONTRACTS.md) ; `generator.py` et `/legacy` restent l'ancien parcours, inchange.
- L'interface permet d'editer les fichiers en memoire (T16) puis de produire le ZIP ou d'ecrire dans un dossier local apres comparaison et confirmation (T17, docs/LOCAL_WRITE.md). Le moteur lui-meme n'ecrit rien. Les editions ne sont acceptees que pour l'ensemble exact des chemins regeneres : changer les skills approuves, les serveurs MCP ou les agents oblige a regenerer l'apercu.
- L'empreinte des skills s'appuie sur les SHA-1 de blobs Git fournis par GitHub (protection anti-collision de GitHub) ; la confiance repose sur l'examen humain du contenu, que l'outil ne remplace pas.
