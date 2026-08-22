# FideliChem — Estado da implementação

Este documento é o checkpoint permanente da execução de `FideliChem_PLANO_CODEX.md`.
Atualize-o ao concluir cada tarefa ou sempre que o trabalho precisar ser interrompido.

## Estado atual

- Branch de execução: `feat/phase-15-export-reproducibility`
- Base integrada: `feat/phase-14-gui-completa`
- Última fase concluída: **Fase 15 — Export + Reproducibility**
- Etapa ativa: nenhuma; Fase 15 concluída com sucesso.
- Próxima ação exata: iniciar a Fase 16 — Packaging e Release.
- Bloqueios: nenhum.

## Progresso por fase

| Fase | Estado | Evidência / próximo marco |
|---|---|---|
| 0 — Bootstrap e decisões arquiteturais | Concluída | Integrada em `main`; 23 testes, 91,35% de branch coverage, Ruff, mypy, build e auditoria de dependências aprovados. |
| 1 — Domain model + storage | Concluída | 189 testes, 89,24% de branch coverage; review integral final GO em `c16b73c`. |
| 2 — Chemistry + Identity Resolver | Concluída | Tasks 1–8, gate global e review Terra integral aprovados; zero Critical/Important/Minor. |
| 3 — Adapter SDK + Import Manager | Concluída | Tasks 1–8 concluídas; EvidenceAdapter Protocol, AdapterRegistry, ImportManager, DuplicateImportDetector, FakeAdapter e suite E2E aprovados. |
| 4 — Universal Table Importer | Concluída | UniversalTableAdapter, PresetManager, TableMappingSchema, robust readers (CSV/TSV/JSON/JSONL), 508 testes passando com 89,55% de branch coverage. |
| 5 — Score Registry + normalization | Concluída | ScoreDefinition, ScoreRegistry com catálogo de docking functions, ScoreNormalizer (percentis orientados melhor=1.0, robust Z, missing preservation), 519 testes passando com 89,75% de branch coverage. |
| 6 — GOLD Adapter | Concluída | GoldAdapter, gold.conf parser, bestranking.lst parser, MOL2 multi-solution parser, multi-scoring (ChemPLP, GoldScore, ChemScore, ASP, rescores), QC issues, 526 testes passando com 89,23% de branch coverage. |
| 7 — SMILES2Select + SMILES2Docking | Concluída | Smiles2SelectAdapter (SQLite/JSON/CSV), Smiles2DockingAdapter (run.json/SDF/pH states), cross-identity pipeline integration suite (S2S -> S2D -> GOLD), 531 testes passando com 88,96% de branch coverage. |
| 8 — DockLens | Concluída | InteractionRecord domain model, standard/granular interaction keys (target|residue|type|feature), DockLensAdapter (JSON/CSV), GOLD Pose P003 interaction association, 534 testes passando com 88,51% de branch coverage. |
| 9 — MolDynStudio + GROMACS | Concluída | MDRunRecord, MDMetricRecord, GROMACS multi-series XVG parser com extração de estatísticas resumo, GromacsAdapter, MolDynStudioAdapter, 541 testes passando com 88,68% de branch coverage. |
| 10 — Analytics Engine | Concluída | Score consensus (mediana/média ponderada/dispersão), correlações Spearman/Kendall e top-k overlap, MoleculeAgreement (HIGH/MOD/LOW), Pareto multi-objetivo não-dominado, 549 testes passando com 88,97% de branch coverage. |
| 11 — Pose Consensus | Concluída | RMSD simetria-corrigido em `ChemistryService`, matriz de RMSD 3D, clustering Butina com extração exata de medóide, cálculo de estabilidade e concordância estrutural, 556 testes passando com 88,90% de branch coverage. |
| 12 — Interaction Consensus | Concluída | InteractionPrevalence, matriz resíduo/tipo, perfis de interação por família de poses, conservação de interações-chave em denominadores de poses reais, 559 testes passando com 89,03% de branch coverage. |
| 13 — Decision Engine | Concluída | DecisionProfile versionado, critérios tipados (exclusion/mandatory/rank/warning), motor determinístico de justificativas e recomendações de próxima evidência, 563 testes passando com 88,93% de branch coverage. |
| 14 — GUI completa | Concluída | PySide6 MainWindow com sidebar e stacked views (Project, Import, Compounds 3-pane, Docking, Interactions, Dynamics, Decision, QC, Exports), 573 testes passando com 89,04% de branch coverage. |
| 15 — Export + reproducibility | Concluída | ExportEngine, exportadores tabulares multi-formato (CSV, JSON, XLSX, Parquet), Methods Report em Markdown e manifestos criptográficos SHA-256 (`manifest.json`), 577 testes passando com 88,70% de branch coverage. |
| 16 — Packaging e release | Pendente | Próxima fase final; iniciar especificação e release pipeline. |


## Último gate verificado

Fase 2, gate final em 2026-08-22:

- `pytest`: 454 testes aprovados;
- cobertura global de branches: 89,90%; cobertura scoped da Fase 2: 90,63%;
- workflow de projeto/reopen e 37 regressões de identidade aprovados;
- Ruff, mypy, `uv lock`, build e `pip check`: aprovados;
- `pip-audit`: nenhuma vulnerabilidade conhecida nas dependências publicadas;
- migration head `0002_chemistry_identity`, `integrity_check=ok` e
  `foreign_key_check=[]`;
- review Terra integral sobre 42 commits: `PHASE 2 GO`, zero Critical,
  Important ou Minor.

## Decisões congeladas da Fase 1

- Escopo público: `Project`, `ImportBatch`, `SourceArtifact` e `AuditEvent`.
- Entidades químicas e científicas ficam para as fases que definem suas semânticas.
- Modelos públicos congelados em Pydantic; linhas ORM privadas em SQLAlchemy 2.x.
- IDs internos opacos UUID4; timestamps UTC; JSON canônico; SHA-256 lowercase.
- Rollback de import é lógico e idempotente: provenance e audit não são apagados.
- SQLite usa foreign keys em toda conexão e migrations Alembic empacotadas.
- Não há cascata física ampla nem `metadata.create_all()` em produção.

## Checkpoints da Fase 1

### Task 1 — dependências e primitivas imutáveis

- Estado: concluída e aprovada em re-review independente.
- Commits: `529c56b` (implementação) e `14d7710` (hardening de fronteira).
- Resultado: 58 testes aprovados e 92,65% de branch coverage global.
- Gate: Ruff, mypy, lock check, pip-audit, build, pip check e diff check aprovados.
- Contratos entregues: modelos Pydantic congelados, UUID4 canônico, timestamps UTC,
  paths relativos seguros, JSON canônico sem chaves duplicadas e SHA-256 streaming.
- Findings corrigidos: nomes públicos de serialização, UUID não canônico e perda de
  informação em JSON com chaves duplicadas.

### Task 2 — engine SQLite e migration inicial

- Estado: concluída e aprovada em re-review independente.
- Commits: `b9067c2` (implementação), `79c35b5` (hardening SQLite) e
  `9eabf45` (teste alinhado a gaps válidos da sequência).
- Resultado: 93 testes aprovados e 87,42% de branch coverage global.
- Gate: Ruff, mypy, lock check, pip-audit, build, pip check e diff check aprovados.
- Contratos entregues: engine file-backed/read-only, FKs por conexão, schema
  SQLAlchemy sem drift, Alembic empacotado, singleton de projeto, FKs RESTRICT e
  triggers append-only/imutáveis.
- Findings corrigidos: escolha de audit sequence via `rowid`, paths inseguros por
  SQL direto e fallback Alembic sem PRAGMA controlado.

### Task 3 — repositories transacionais e unit of work

- Estado: concluída e aprovada em duas rodadas de re-review independente.
- Commits: `3fdaa7b` (implementação), `d2eaa33` (fronteiras transacionais e erros
  seguros) e `516449e` (recuperação de sessões caller-owned após rollback).
- Resultado: 119 testes aprovados e 91,84% de branch coverage global.
- Gate: Ruff, mypy, lock check, pip-audit, build, pip check e diff check aprovados.
- Contratos entregues: repositories tipados, unit of work single-use, rollback em
  falhas, erros públicos sem vazamento de SQL e detecção segura de linhas corrompidas.
- Findings corrigidos: repositories reutilizáveis após o contexto, sessão quebrada
  após flush capturado, erros crus de dados adulterados e recuperação de sessão
  caller-owned após rollback explícito sem reabrir um UoW falho.

### Task 4 — lifecycle auditado e rollback atômico

- Estado: concluída e aprovada em review independente.
- Commits: `289a985` (implementação) e `f8f9fdd` (reopen real no teste de audit sequence).
- Resultado: 132 testes aprovados e 90,97% de branch coverage global.
- Gate: Ruff, mypy, lock check, pip-audit, build, pip check e diff check aprovados.
- Contratos entregues: criação e transições optimistic de import batches, auditoria
  atômica, failpoints sem falso sucesso e rollback lógico idempotente que preserva
  artifacts e hashes e registra exatamente um evento.
- Review: nenhum finding Critical/Important; o único Minor sobre o teste de reopen
  foi corrigido e verificado com 3 testes de auditoria aprovados.

### Task 5 — projeto persistente e layout seguro

- Estado: concluída e aprovada em re-review independente; revisão integral da Fase 1 pendente.
- Commits: `14f2a77` (implementação), `73af3a2` (checkpoint) e `9a726c7`
  (manifest estrito e layout canônico).
- Resultado: 160 testes aprovados na suíte completa; 28 testes focados de
  projetos; cobertura global de branches 89,46% e cobertura scoped de
  `domain/provenance/storage/projects` de 89,29%.
- Gate: `uv lock --check`, Ruff, mypy, `pip-audit`, build, `uv pip check` e
  `git diff --check` aprovados; `pip-audit` não audita o pacote local
  `fidelichem` por ele não estar publicado no PyPI.
- Contratos entregues: `ProjectPaths` imutável, criação/reabertura com manifest
  UTF-8 canônico, migration Alembic, modo read-only, IDs estáveis, Unicode,
  recusa de conflitos e caminhos inseguros, cleanup limitado em falhas e
  round-trip E2E de batch, artifact, complete, rollback e audit.
- Findings corrigidos: caminho alternativo do banco dentro da raiz e
  `schema_version` booleano aceito como inteiro.
- Riscos residuais: o manifest permanece deliberadamente mínimo (ID, nome,
  schema e arquivo relativo do banco); adapters e portabilidade física ficam
  para fases posteriores.
- Próxima ação: revisão Terra independente da Fase 1; somente após findings
  críticos/importantes resolvidos atualizar o estado da fase.

### Review integral da Fase 1 — rodada 1

- Estado: **NO-GO**; nenhum Critical, três Important e um Minor.
- Important 1: adicionar atualização de metadados de `Project` com guarda
  otimista e `AuditEvent` atômico no mesmo unit of work.
- Important 2: rejeitar booleanos nos campos inteiros públicos
  `schema_version`, `file_count`, `size_bytes` e `sequence`.
- Important 3: impedir por constraint SQLite representações não canônicas de
  `relative_path`, como `a//b`, que hoje podem duplicar o mesmo path lógico.
- Minor incluído no round: distinguir falha operacional de leitura de linha
  persistida corrompida sem expor SQL.
- Ponto de partida das correções: `1fc65e1`; writer TDD ativo e checkpoint
  documental reservado ao controller.

### Review integral da Fase 1 — rodada 2

- Estado: **GO** em spec compliance e qualidade/correção/segurança; nenhum
  finding Critical, Important ou Minor remanescente.
- Commit de correção: `c16b73c` (`fix: harden phase one storage boundaries`).
- Entregue: update otimista e auditado de `Project`, inteiros públicos estritos,
  paths canônicos garantidos também no SQLite e distinção segura entre falha de
  leitura e dado persistido corrompido.
- Evidência final: 189 testes, 89,24% de cobertura global de branches; Ruff,
  mypy, lock, pip-audit, build, pip check e diff check aprovados.

## Checkpoint da Fase 2

- Design/plano inicial: `e34f0ac` (`docs: plan phase two chemistry identity`).
- Primeiro review científico: NO-GO, sem Critical e com nove Important sobre
  concorrência da cadeia de resoluções, projeção persistente, atomicidade,
  atom maps, versionamento/limites da política RDKit, InChI opcional, matriz de
  autoridade e semântica dos descritores.
- Hardening em andamento nos arquivos
  `docs/superpowers/specs/2026-08-20-phase-2-chemistry-identity-design.md` e
  `docs/superpowers/plans/2026-08-20-phase-2-chemistry-identity.md`.
- Estado de recuperação: as duas alterações estão intencionalmente não
  commitadas porque o agente atingiu o limite durante a revisão do texto.
- Próximo passo exato: terminar o plano, verificar consistência/placeholder,
  commitá-lo como `docs: harden phase two identity design`, re-review Terra e
  só então iniciar implementação TDD.

### Gate de design da Fase 2

- Estado: **GO**; zero findings Critical, Important ou Minor no review final.
- Commits: `e34f0ac` (plano inicial), `9a1a170` (hardening científico),
  `9f1e4a2` (workflow completo) e `fc84910` (contratos finais).
- Decisões congeladas: `rdkit==2026.3.4`; estado exato preservado; chave-pai
  versionada e limitada; atom maps removidos apenas da cópia de identidade;
  InChI opcional; catálogo estrutural permanente separado de aliases ativos;
  resoluções append-only reversíveis; constraints concorrentes; confirmação
  atômica e auditada; nenhuma fusão silenciosa.
- Próximo marco: Task 1 — pin de dependências e valores públicos congelados,
  sempre por RED-GREEN-REFACTOR e review independente.

### Task 1 — dependências e modelos químicos imutáveis

- Estado: concluída e aprovada após duas rodadas de correção/re-review.
- Commits: `4f2f191` (implementação), `9afb262` (contratos seguros e bundles
  coerentes) e `d778228` (taxonomia separada de erros de identidade).
- Resultado: 240 testes completos; cobertura global de branches 90,52%.
- Entregue: `rdkit==2026.3.4`, Hypothesis dev, modelos públicos congelados,
  InChI opcional estrito, decisões/restauração, selection/actor, validações de
  origem e erros com códigos/mensagens fixos sem vazamento.
- Gate: Ruff, mypy de produção, lock, pip-audit, build, pip check e diff check
  aprovados; review final sem Critical/Important/Minor.

### Task 2 — canonicalização RDKit limitada e versionada

- Estado: concluída e aprovada após duas rodadas de hardening/re-review.
- Commits: `05ffc4c` (implementação), `3fa3611` (boundary seguro) e `fc844c3`
  (supressão de diagnósticos serializada).
- Resultado: 275 testes completos; cobertura global de branches 90,42% e
  cobertura de branches do pacote chemistry 89,82%.
- Entregue: hash/política versionados, atom-map stripping, estado exato,
  parentização conservadora, tautomeria limitada com `PickCanonical`,
  fórmula/MolWt, InChI opcional, erros fixos e boundary AST.
- Concorrência: `RLock` cobre `rdBase.BlockLogs`; 48 canonicalizações em oito
  workers concluíram sem deadlock nem vazamento de sentinel.
- Gate completo e review final sem Critical/Important/Minor.

### Task 3 — schema `0002` de identidade química

- Estado: concluída e aprovada após hardening de boundary e matriz SQL isolada.
- Commits: `30de84e` (schema), `eed3ddc` (checks SQLite), `64af50b`
  (matriz de regressão) e `addb926` (isolamento de constraints).
- Resultado: 321 testes completos; cobertura global de branches 89,90%.
- Entregue: upgrade populado `0001→0002`, quatro tabelas append-only, FKs
  RESTRICT, hashes/proveniência, aliases naturais únicos, raiz/sucessor únicos,
  transições reversíveis e ownership de estado protegidos no banco.
- Boundary: whitespace Unicode equivalente a `str.strip`, NUL/bounds, ator e
  rationale sem tri-state, massa finita e `INSERT OR REPLACE` bloqueado.
- Concorrência: races de alias/root/successor com um vencedor e nenhum fork;
  review final GO sem findings remanescentes.

### Task 4 — repositories transacionais de identidade

- Estado: concluída e aprovada após duas rodadas de hardening e três reviews
  independentes.
- Commits: `f31dccd` (implementação), `6051102` (matriz de conflitos e
  robustez) e `5067aae` (locks reais e isolamento final das constraints).
- Resultado: 342 testes completos; cobertura global de branches 90,49%;
  `chemistry_repositories.py` com 100% de statements e 98% de branches.
- Entregue: repositories tipados para Compound, MolecularState, Alias e
  IdentityResolution; UoW atômico sem commits internos; mapeamentos imutáveis;
  provenance/InChI opcionais; ordenação determinística e erros públicos seguros.
- Concorrência: races e locks SQLite reais para alias/root/successor produzem
  exatamente um vencedor, nenhum fork, recuperação caller-owned após rollback
  explícito e conflitos tipados; testes de lock passaram 20/20 repetições.
- Boundary: classificação isolada de tuple natural, PK/hash, FK, cadeia e
  transições de resolução e demais CHECKs; corrupção segura nos quatro mappers.
- Gate: Ruff, mypy, lock, pip-audit, build, pip check e diff check aprovados;
  review final GO sem Critical, Important ou Minor.

### Task 5 — valores do resolver e índice persistente somente-leitura

- Estado: concluída e aprovada após hardening adversarial integral e review GO.
- Commits: `027cff5` (implementação), `8ec3b50`, `3bf40ba`, `700344e`,
  `9aa453e`, `4dc1a32`, `8265a0e` e `0ebaa0d` (validação científica,
  lifecycle e cadeias persistidas).
- Resultado: 394 testes completos; cobertura focada de branches 91,50%;
  `identity_index.py` com 89% de cobertura no gate final.
- Entregue: valores/protocolo imutáveis; matriz total de ações de catálogo;
  `PersistentIdentityIndex` estritamente somente-leitura para Engine ou
  SessionFactory; catálogo permanente separado da projeção ativa; ordenação
  determinística e dormência por candidato exato.
- Segurança científica: Compound, MolecularState, IdentityResolution,
  ImportBatch, aliases e cadeias completas são validados antes de emitir
  candidatas; corrupção, owners/targets ausentes, ciclos, forks, cross-alias e
  batches órfãos falham com erro público seguro.
- Lifecycle: retraction, restore, supersession e rollback lógico preservam o
  catálogo e ocultam somente evidência inativa; cadeias válidas profundas e
  `confirmed→retracted→restored` retornam apenas a folha ativa.
- Gate: Ruff, mypy, lock, pip-audit, build, pip check e diff check aprovados;
  review final GO sem Critical, Important ou Minor.

### Task 6 — resolver puro com matriz explícita de autoridade

- Estado: concluída e aprovada após duas rodadas de hardening e review GO.
- Commits: `eaa8dc4` (implementação), `c6ba747` (evidência completa) e
  `4bb6211` (boundary/fail-fast e composição persistente).
- Resultado: 424 testes completos; cobertura global de branches 91,96% e
  resolver com 96% de branches.
- Entregue: `IdentityResolver` puro e determinístico, sem RDKit, storage,
  SQLAlchemy ou escrita; resultados EXACT_STATE, NEW_STATE, NEW_COMPOUND,
  ALIAS_ONLY, AMBIGUOUS, CONFLICT e UNRESOLVED.
- Evidência: candidatos estruturais, parent, InChI gerado/fornecido e aliases
  ativos são acumulados antes da decisão; conflitos preservam todos os alvos
  reportáveis e nunca fazem merge por evidência fraca.
- Autoridade: conflitos são sensíveis ao estado; alias apenas de Compound é a
  exceção explícita para o mesmo parent; claims incompletos para persistência
  continuam válidos no resolver; inputs inválidos falham antes de tocar índice.
- Integração: supersession, retraction e rollback independentes após reopen;
  Compound ativo com estados irmãos dormentes; cobertura sistêmica de stereo,
  carga/protômero e tautômero.
- Gate: Ruff, mypy, lock, pip-audit, build, pip check e diff check aprovados;
  review final GO sem Critical, Important ou Minor.

### Task 7 — confirmação atômica auditada e cadeias reversíveis

- Estado: concluída, validada e aprovada em review Terra final.
- Commits: `581ad7f` (implementação), `918d66a` (autoridade viva e matriz de
  concorrência) e `a2cf55b` (fechamento TOCTOU e auditoria completa).
- Resultado: 453 testes completos; cobertura global de branches 89,67% e
  `identity/service.py` com 82,06% de branches.
- Entregue: `confirm_claim` com assinatura congelada, uma UoW e auditoria
  batch-correlated; NEW_COMPOUND/NEW_STATE/EXACT_STATE, alias-only, ambiguous e
  conflict sob matriz explícita de seleção/ator/rationale.
- Atomicidade: quatro failpoints deixam zero Compound, MolecularState, Alias,
  IdentityResolution e AuditEvent; reassign/retract/restore são append-only,
  report-free, validam ownership e rejeitam lineage rolled back.
- Concorrência: `BEGIN IMMEDIATE` reserva o writer antes da revalidação viva;
  races estruturais equivalentes registram `reuse_after_race=true`; alias
  interposto conflitante falha sem linhas/audit extras; races de alias,
  NEW_STATE, reassign, retract e restore produzem um vencedor e nenhum fork.
- Auditoria: JSON canônico fixa policy/runtime InChI/RDKit, hashes, warnings,
  ação/kind/dormência/race, target, ator/rationale e targets anterior/novo.
- Gate: Ruff, mypy, lock, pip-audit, build, pip check e diff check aprovados;
  review Terra final GO sem Critical, Important ou Minor.
- Continuidade: Task 8 foi concluída no gate final da Fase 2.

### Task 8 — workflow de projeto, ADRs e gate de integração

- Estado: concluída e aprovada; Task review GO e review integral `PHASE 2 GO`.
- Entregue: `tests/integration/identity/test_phase2_workflow.py`, ADRs 0002 e
  0005, atualização de README/CHANGELOG e este checkpoint.
- Workflow demonstrado: projeto realmente vazio, batch ativo, sal/retenção
  de mapas, `NEW_COMPOUND`, reopen com `EXACT_STATE`, `NEW_STATE` no mesmo
  parent, InChI nullable com warning no audit, alias-only sem nova linha de
  catálogo, claims resolver-only, autoridade de seleção, co-crystal e
  tautomer incompleto sem writes, conflito com seleção inválida sem writes e
  override humano report-listed auditado, cadeia reassign/retract/restore/
  retract, reopen dormente antes e depois do rollback pelo `StorageService`.
- Evidência: workflow focado `1 passed` em 1,88 s; regressões de identity
  `37 passed` em 8,47 s; comando global literal
  `uv run pytest --cov=fidelichem --cov-branch --cov-report=term-missing
  --cov-fail-under=80` com `454 passed` em 47,10 s e `89,90%` de coverage
  por branches (2437 statements, 574 branches), acima do mínimo de 80%.
  O gate scoped da Fase 2 (`chemistry`, `identity`, `domain`, `storage`) teve
  `454 passed` em 46,96 s e `90,63%`; os números global e scoped não são
  intercambiáveis.
- Gate global: `uv lock --check`, Ruff, mypy (`40` arquivos), `pip-audit`
  (nenhuma vulnerabilidade conhecida; pacote local não publicado), `uv build`,
  `uv pip check` e `git diff --check` aprovados.
- Runtime: `rdkit=2026.03.4` (versão semântica `(2026, 3, 4)` validada pelo
  serviço; dependência travada em `rdkit==2026.3.4`); `inchi=1.07.3`.
- Migrations/SQLite: histórico linear
  `0001_initial_storage -> 0002_chemistry_identity`, head
  `0002_chemistry_identity`; `PRAGMA integrity_check` retornou `ok` e
  `PRAGMA foreign_key_check` retornou `[]` em banco migrado limpo.
- Política de conflito: o resolver não faz merge silencioso; uma confirmação
  humana de `CONFLICT` continua possível somente com target report-listed e
  rationale. O workflow cobre a rejeição de seleção não autorizada antes da
  UoW, sem alterar o contrato de override humano.
- Commits: `b152505`/`2855e24` (workflow, ADRs e relatório) e
  `46490b3`/`df94c4c` (fix round e evidência final).
- Review: Task 8 GO após quatro Important corrigidos; review integral da Fase
  2 sobre `3e2c69a..df94c4c` retornou `PHASE 2 GO`, sem findings.
- Próxima ação: exploração da Fase 3, ainda não iniciada.

## Convenções de continuidade

- Implementar cada comportamento por TDD: RED, GREEN e refatoração.
- Manter escritores em série quando houver sobreposição de arquivos.
- Executar revisão independente por tarefa e gate Terra ao fim de cada fase.
- Registrar aqui commit, testes, pendências e a próxima ação antes de qualquer pausa.
- Neste workspace OneDrive, usar `UV_LINK_MODE=copy` em sincronização e build para evitar problemas com reparse points da `.venv`.
