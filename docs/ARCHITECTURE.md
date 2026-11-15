# Architecture cible - Forge-my-Project

## Etat actuel
Prototype en Python standard library: server.py expose le formulaire ui/index.html et ses assets; generator.py conserve la facade publique historique. La validation et la generation historiques sont isolees dans forge/config/legacy.py et forge/generator/legacy.py; leurs textes sont dans templates/legacy/. Le prototype ne satisfait pas encore toutes les specifications. Conserver son fonctionnement pendant la migration et ne pas annoncer les modules cibles comme implementes.

Moteur technique (T06-T11) disponible dans forge/ avec catalogs/ et templates/ : schema d'entree, catalogue et compatibilites, regles, rendu des documents, verification des packages et skills. Il alimente le formulaire hybride servi sur / (API locale /api/catalog, /api/plan, /api/archive dans forge/web.py) ; le formulaire historique reste sur /legacy via generator.py. Profils predefinis dans catalogs/profiles/, profils personnels et reponses partielles geres par forge/config/profiles.py et forge/config/answers.py (T05). T16 ajoute l'explorateur/editeur en memoire et la validation pure dans `forge/filesystem/preview.py`; T17 ajoute la destination, la comparaison et l'ecriture confirmee (`forge/filesystem/{destination,compare,content,writer,workflow}.py`). Contrat et limites : docs/ENGINE.md et docs/CONTRACTS.md.

## Flux cible
```text
UI locale (Firefox) -> questionnaire conditionnel / profils
  -> schema versionne / validation
  -> planificateur de regles et compatibilites
  -> catalogues et templates externes versionnes
  -> selection skills / verification packages, versions et MCP optionnels
  -> rendu deterministe des documents, hooks, workflows
  -> audit des fichiers / apercu arbre + edition + diff
  -> validation explicite / sauvegarde + ecriture atomique dans dossier choisi
  -> rapport et logs expurges
```

## Arborescence cible (a creer progressivement)
```text
Forge-my-Project/
  AGENTS.md
  README.md
  TODO.md
  docs/
    SPECIFICATIONS.md
    ARCHITECTURE.md
    DEVELOPMENT_PLAN.md
    FINALIZATION_PLAN.md
    SECURITY.md
    TESTING.md
    DECISIONS/
  forge/
    config/
    rules/
    planner/
    generator/
    skills/
    verification/
    security/
    filesystem/
  ui/
    index.html
    css/
    js/
  templates/
    agents/
    documentation/
    architecture/
    skills/
    hooks/
    ci/
  catalogs/
    technologies/
    security/
    profiles/
  tests/
  .agents/skills/
  .github/workflows/
  .githooks/
```

## Contrats
- config: normalise et valide les informations de l'utilisateur; schema versionne.
- rules/planner: propose une architecture et une liste de fichiers; signale conflits et lacunes; aucune IA.
- templates/catalogs: donnees externes versionnees, validees avant utilisation, jamais executees comme commandes.
- skills: recuperation depuis my-skills par Git/gh, source authentifiee et verification; externes soumis a approbation.
- verification/security: controle des dependances, API, licences, vulnérabilites, CI et hooks; etat PASS/FAIL/NON VERIFIE.
- filesystem: simulation/diff, protection contre sorties de repertoire, sauvegarde et ecriture controlee, jamais de remplacement implicite.
- UI: ne detient pas la logique de confiance; toute requete est revalidee cote serveur.

Les signatures, formats et responsabilites applicables sont definis dans [CONTRACTS.md](CONTRACTS.md). `generator.py`, `server.py`, `GET /` et `POST /generate` sont les points de compatibilite pendant la migration.

## Mise en place progressive
- Operationnel apres T02: ui/, forge/config/legacy.py, forge/generator/legacy.py et templates/legacy/.
- Reserve aux taches T06-T11 de Claude: forge/rules/, forge/planner/, catalogues, moteur de rendu moderne, skills et verification des dependances. T02 ne cree pas de coquilles vides pour ces composants.
- Operationnel apres T16: `forge/filesystem/preview.py` valide les chemins, l'ensemble exact et la taille des contenus edites; `content.py` controle leur contenu.
- Operationnel apres T17: `destination.py` (racine autorisee, parcours par descripteurs O_NOFOLLOW), `compare.py` (etats, diff), `workflow.py` (jeton HMAC, decisions, confirmation), `writer.py` (sauvegarde, ecriture atomique, rollback). Independant du transport HTTP; `forge/web.py` ne fait que relayer.
- La bibliotheque templates/legacy preserve strictement les sorties actuelles. Les futurs templates structures peuvent coexister puis remplacer la facade par migration testee.

## Frontieres de securite
Serveur borne a 127.0.0.1. Les champs, modeles, depots distants et fichiers existants sont non fiables. Refuser la traversee de chemins, l'injection de commandes, les scripts non approuves et la divulgation d'identifiants. Les acces reseau aux registres, skills et MCP sont explicites, journalises et soumis aux regles d'autorisation. Aucun acces distant aux dossiers utilisateur sans validation.

## Decisions
- Aucun LLM integre, ni hebergement.
- Aucune creation ni push du depot du projet cible.
- Python et UI web legere retenus pour le moteur.
- Evolution progressive des scripts existants avec tests de non-regression.
