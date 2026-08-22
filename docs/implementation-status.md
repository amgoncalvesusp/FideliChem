# FideliChem — Estado da implementação

Este documento é o checkpoint permanente da execução de `FideliChem_PLANO_CODEX.md`.
Atualize-o ao concluir cada tarefa ou sempre que o trabalho precisar ser interrompido.

## Estado atual

- Branch de execução: `feat/fidelichem-mvp-phases-1-16`
- Base integrada: `main` em `3ad80bc`
- Fase ativa: **Fase 2 — Chemistry + Identity Resolver**
- Etapa ativa: Task 7 — confirmação atômica auditada e cadeias reversíveis
- Próxima ação exata: implementar por TDD a Task 7 de `docs/superpowers/plans/2026-08-20-phase-2-chemistry-identity.md` a partir de `4bb6211`.
- Bloqueios: nenhum.

## Progresso por fase

| Fase | Estado | Evidência / próximo marco |
|---|---|---|
| 0 — Bootstrap e decisões arquiteturais | Concluída | Integrada em `main`; 23 testes, 91,35% de branch coverage, Ruff, mypy, build e auditoria de dependências aprovados. |
| 1 — Domain model + storage | Concluída | 189 testes, 89,24% de branch coverage; review integral final GO em `c16b73c`. |
| 2 — Chemistry + Identity Resolver | Em andamento | Tasks 1–6 concluídas; Task 7 (serviço atômico/auditado) é o próximo marco. |
| 3 — Adapter SDK + Import Manager | Pendente | Aguardar gate Terra da Fase 2. |
| 4 — Universal Table Importer | Pendente | Aguardar gate Terra da Fase 3. |
| 5 — Score Registry + normalization | Pendente | Aguardar gate Terra da Fase 4. |
| 6 — GOLD Adapter | Pendente | Aguardar gate Terra da Fase 5. |
| 7 — SMILES2Select + SMILES2Docking | Pendente | Aguardar gate Terra da Fase 6. |
| 8 — DockLens | Pendente | Aguardar gate Terra da Fase 7. |
| 9 — MolDynStudio + GROMACS | Pendente | Aguardar gate Terra da Fase 8. |
| 10 — Analytics Engine | Pendente | Aguardar gate Terra da Fase 9. |
| 11 — Pose Consensus | Pendente | Aguardar gate Terra da Fase 10. |
| 12 — Interaction Consensus | Pendente | Aguardar gate Terra da Fase 11. |
| 13 — Decision Engine | Pendente | Aguardar gate Terra da Fase 12. |
| 14 — GUI completa | Pendente | Aguardar gate Terra da Fase 13. |
| 15 — Export + reproducibility | Pendente | Aguardar gate Terra da Fase 14. |
| 16 — Packaging e release | Pendente | Aguardar gate Terra da Fase 15. |

## Último gate verificado

Fase 1, gate final em 2026-08-20:

- `pytest`: 189 testes aprovados;
- cobertura global de branches: 89,24%;
- cobertura scoped de `domain/provenance/storage/projects`: 89,07% (166 testes);
- Ruff e mypy: aprovados;
- `uv lock`, build e `pip check`: aprovados;
- `pip-audit`: nenhuma vulnerabilidade conhecida nas dependências publicadas;
- working tree e `git diff --check`: limpos.

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

## Convenções de continuidade

- Implementar cada comportamento por TDD: RED, GREEN e refatoração.
- Manter escritores em série quando houver sobreposição de arquivos.
- Executar revisão independente por tarefa e gate Terra ao fim de cada fase.
- Registrar aqui commit, testes, pendências e a próxima ação antes de qualquer pausa.
- Neste workspace OneDrive, usar `UV_LINK_MODE=copy` em sincronização e build para evitar problemas com reparse points da `.venv`.
