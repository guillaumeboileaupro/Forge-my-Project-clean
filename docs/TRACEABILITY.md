# Matrice de tracabilite exigences -> implementation -> tests

Reference : docs/SPECIFICATIONS.md (valide le 14 novembre 2026). Etat au 15 novembre 2026, apres T17 et la cloture de T03/T04.
Statuts : PASS (implemente et prouve par un test execute), PARTIEL (implemente avec une limite explicite), NON VERIFIE (aucune preuve executable). Les tests cites sont dans `tests/` ; « Firefox » designe `tests/test_e2e_firefox.py` (FORGE_E2E=1).

## Les « 40 choix confirmes »
docs/FINALIZATION_PLAN.md et la PR #3 mentionnent 40 questions/choix valides par l'utilisateur. Leur liste n'existe dans aucun fichier, commit, branche (`docs/validated-project-specification`, `docs/development-roadmap-todo`) ni description de PR du depot : seule leur synthese, docs/SPECIFICATIONS.md, a ete versionnee. Ces 40 decisions ne sont donc pas retracables une par une et n'ont pas ete reconstituees. La matrice ci-dessous trace chaque exigence de SPECIFICATIONS.md ; si la liste originale est retrouvee, la comparer a cette matrice.

## Mission et limites
| ID | Exigence | Implementation | Preuves | Statut |
| --- | --- | --- | --- | --- |
| M1 | Outil local, UI Firefox, sans hebergement ni LLM | server.py (127.0.0.1), ui/ | test_server, test_web_api.test_transport_guards, Firefox (10 parcours) | PASS |
| M2 | Ecrit uniquement dans un dossier choisi, apres confirmation | forge/filesystem (T17) | test_filesystem_write (21), test_web_api.test_local_write_flow_compare_confirm_backup, test_preview_routes_never_write_to_disk, Firefox test_local_write_journey | PASS |
| M3 | Pas de code metier | templates/stack (points d'entree vides, tests de fumee) | test_engine_documents.test_every_output_is_safe_documentation_without_business_code, test_code_files_are_empty_entry_points_and_smoke_tests_only | PASS |
| M4 | Ne cree pas le depot GitHub, ne pousse pas | aucun appel d'ecriture GitHub ; `gh` en lecture seule pour les skills | test_engine_skills.test_read_only_invocation_without_shell ; revue : aucun `git push`/`gh repo create` dans forge/ | PASS |

## Experience utilisateur
| ID | Exigence | Implementation | Preuves | Statut |
| --- | --- | --- | --- | --- |
| U1 | Questionnaire par sections, progressif, conditionnel, retour arriere | ui/index.html (6 sections), app.js `updateConditional`, `showStep` | Firefox test_questionnaire_search_suggestion_and_warning_confirmation, test_full_journey, test_autosave_restores_conditional_answers | PASS |
| U2 | Description libre + champs structures | `description` (2000), `architecture` (4000), champs du schema | test_profiles.test_text_is_data_only, test_engine_rules.test_user_values_are_not_reinterpreted | PASS |
| U3 | Architecture manuelle ou suggeree par regles locales, toujours modifiable | plan.architecture ; bouton « Proposer l'architecture » (T04) ; editeur T16 | test_web_api.test_plan_exposes_editable_architecture_suggestion, test_engine_documents.test_unknown_commands_and_architecture_are_explicit, Firefox test_questionnaire_... | PASS |
| U4 | Contenus prepares hors outil colles dans le formulaire | champs texte, jamais interpretes | test_engine_rules.test_user_values_are_not_reinterpreted | PASS |
| U5 | Navigation laterale, recherche, progression, indicateurs d'erreur | sidebar, `#tech-search` (T03), `<progress>`, badges | Firefox test_questionnaire_... (recherche), test_full_journey (badges) | PASS |
| U6 | Profils predefinis et personnels | catalogs/profiles (6), forge/config/profiles.py | test_profiles (17), Firefox test_profiles_lifecycle | PASS |
| U7 | Sauvegarde automatique locale, import/export JSON valide | localStorage revalide, /api/answers/validate | Firefox test_autosave_..., test_export_then_import, test_incompatible_draft_is_not_restored | PASS |
| U8 | Apercu arbre + contenu, edition avant ecriture | T16 | test_filesystem_preview, test_web_api.test_edited_preview_*, Firefox test_full_journey | PASS |
| U9 | Comparaison, fusion assistee, sauvegarde, validation explicite | T17 | test_filesystem_write.test_keep_replace_and_manual_merge, Firefox test_local_write_journey | PARTIEL : fusion manuelle guidee par diff, pas de fusion a trois voies |
| U10 | Nouveau ou existant ; aucune modification hors destination | destination.py (O_NOFOLLOW, racine autorisee) | test_filesystem_write.test_dangerous_destinations_are_refused, test_symlink_*, test_new_destination_is_created | PASS |
| U11 | Diagnostics lisibles, logs locaux sans secrets, rapport de generation | renderReport, rapport T17, journal du serveur (ligne de requete seulement) | test_web_api.test_server_log_never_contains_request_bodies, test_local_write_flow_... (journal) | PASS |

## Sorties obligatoires
| ID | Exigence | Implementation | Preuves | Statut |
| --- | --- | --- | --- | --- |
| S1 | AGENTS.md detaille (mission, architecture, conventions, commandes, agents, skills, securite, erreurs, workflow, DoD) | templates/agents/AGENTS.md.tmpl, catalogs/rules/base.json | test_engine_documents.test_agents_md_is_specific | PASS |
| S2 | Skills utiles adaptes aux agents | forge/skills (my-skills T09, externes T10) | test_engine_skills, test_engine_external_skills, test_skills_api | PASS |
| S3 | ARCHITECTURE, DEVELOPMENT_PLAN, TODO (taches, dependances, estimations, reel, ecarts) | templates/documentation | test_engine_documents.test_todo_has_tracking_columns_and_no_invented_estimate, test_expected_files | PASS |
| S4 | README, SECURITY, CONTRIBUTING, TESTING, DEPENDENCIES, ADR, DEPLOYMENT si applicable | templates/documentation, rule deployment-docker | test_engine_documents.test_expected_files, test_optional_outputs_require_opt_in | PASS |
| S5 | Hooks Git + hooks d'agents selon capacites reelles | T14 | test_engine_hooks (15, dont hooks executes dans un vrai depot) | PASS |
| S6 | GitHub Actions operationnelles, qualite, tests, couverture et seuils | T12, ci.yml.tmpl, seuils pytest-cov / vitest | test_engine_ci, test_engine_documents.test_workflow_is_pinned_and_least_privilege, job CI `generated-projects` (6 profils) | PASS |
| S7 | Tests integration, E2E/recette, non-regression quand applicables | TESTING.md genere (politique) | test_engine_documents.test_expected_files | PARTIEL : pas de harnais E2E genere, le projet initialise n'a pas encore de parcours utilisateur |
| S8 | Securite stricte : secrets, SAST, SCA, supply chain, SBOM si applicable, echec bloquant | T13, catalogs/security | test_engine_security (7), smoke_security.py (job CI) | PASS (SBOM au niveau `hardened`) |

## Sorties optionnelles, sources et templates
| ID | Exigence | Implementation | Preuves | Statut |
| --- | --- | --- | --- | --- |
| O1 | MCP seulement si necessaire, verifie, permissions minimales, valide par l'utilisateur | T15 | test_engine_mcp (11), Firefox test_mcp_selection | PASS |
| O2 | Deploiement seulement si pertinent | rule deployment-docker (opt-in) | test_engine_documents.test_optional_outputs_require_opt_in | PASS |
| T1 | Modeles externes versionnes et editables | templates/, catalogs/ | test_engine_documents.test_rules_and_templates_load, test_generator.test_templates_are_external_... | PASS |
| T2 | Regles de base + regles stack/agents | catalogs/rules | test_engine_rules.test_composition_is_conditional_ordered_and_deduplicated, test_mandatory_rule_required | PASS |
| T3 | Catalogue extensible, versions stables, versions choisies, compatibilite | catalogs/technologies, forge/config | test_engine_catalog (15), test_engine_ci.test_stable_versions_* | PASS |
| T4 | my-skills via l'authentification gh, sans la supposer | forge/skills/github.py | test_engine_skills.test_read_only_invocation_without_shell, test_offline_source_is_unverified_warning | PASS |
| T5 | Skills externes : provenance, contenu, validation utilisateur | T10 | test_engine_external_skills (14), Firefox test_external_skills_approval | PASS |
| T6 | Jamais de script distant non approuve ni de package invente | copie texte seule ; registres | test_engine_skills.test_scripts_are_never_downloaded, test_engine_verification.test_fictional_package_and_versions_fail | PASS |

## Workflow genere
| ID | Exigence | Implementation | Preuves | Statut |
| --- | --- | --- | --- | --- |
| W1 | Un agent, une PR, branche dediee, pas de commit sur main, CI verte, temps, nettoyage | base.json `workflow`, hooks | test_engine_documents.test_agents_md_is_specific, test_engine_hooks | PASS |
| W2 | Permissions et regles de branche effectivement configurees a distance | CONTRIBUTING.md : commande `gh api` de protection de `main` (T04), controles requis = jobs de la CI | test_engine_documents.test_contributing_gives_a_branch_protection_command_matching_ci_jobs | PARTIEL : l'outil ne pousse pas (non-objectif) ; la commande doit etre executee par le proprietaire ; depot prive gratuit non protegeable (documentation GitHub) |

## Verification et erreurs
| ID | Exigence | Implementation | Preuves | Statut |
| --- | --- | --- | --- | --- |
| V1 | Bouton « Verifier la configuration » et controles repetes avant ecriture | `#check`, archive/compare/apply regenerent | test_web_api.test_archive_repeats_verification_and_blocks_errors, test_skills_api.test_local_write_preserves_approved_skill_and_mcp | PASS |
| V2 | Preuves explicites ; impossible a verifier = NON VERIFIE | forge/verification | test_engine_verification.test_registry_unavailable_is_not_pass, test_offline_registry_gives_warnings_not_pass | PASS |
| V3 | Erreur critique = blocage | diagnostics ERROR | test_engine_verification.test_vulnerable_or_fictional_dependency_blocks_generation, test_engine_catalog.test_conflict | PASS |
| V4 | Element optionnel absent = avertissement et confirmation | case « J'ai pris connaissance des avertissements » avant validation (T04) | Firefox test_questionnaire_search_suggestion_and_warning_confirmation | PASS |
| V5 | Aucune ecriture sans validation finale ; journal genere / ignore / non verifie / echec | T17, `report.journal` (T04) | test_web_api.test_local_write_flow_compare_confirm_backup | PASS |

## Non-objectifs
| ID | Exigence | Preuves | Statut |
| --- | --- | --- | --- |
| N1 | Pas de code metier | M3 | PASS |
| N2 | Pas d'IA embarquee | aucune dependance ni appel reseau hors liste blanche HTTPS (registres, GitHub, registre MCP) | test_engine_verification.test_only_https_allowlisted_hosts | PASS |
| N3 | Pas de publication / deploiement automatique | M4 | PASS |
| N4 | Pas de synchronisation apres initialisation | aucune fonction de mise a jour d'un projet cible | revue du code | PASS |

## Ecarts corriges pendant la cloture de T03/T04
- U5 : recherche absente dans le questionnaire -> filtre des technologies, sans perte des choix.
- U3 : suggestion d'architecture visible seulement dans les fichiers generes -> reprise dans le formulaire, modifiable.
- V4 : avertissements affiches sans confirmation -> confirmation explicite exigee avant validation des fichiers.
- V5 : journal final sans « genere » ni « ignore » -> journal complet.
- W2 : regles de branche seulement mentionnees -> commande verifiee (API REST GitHub « Update branch protection ») dans CONTRIBUTING.md.
- U11 : absence de preuve sur les logs -> test : le journal du serveur ne contient jamais le corps des requetes.
