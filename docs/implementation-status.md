# FideliChem — Estado da implementação

Este documento é o checkpoint permanente da execução de `FideliChem_PLANO_CODEX.md`.
Atualize-o ao concluir cada tarefa ou sempre que o trabalho precisar ser interrompido.

## Estado atual

- Branch de execução: `feat/fidelichem-mvp-phases-1-16`
- Base integrada: `main` em `3ad80bc`
- Fase ativa: **Fase 1 — Domain model + storage**
- Etapa ativa: Task 5 — layout seguro de projeto e gate integrado
- Próxima ação exata: implementar por TDD a Task 5 de `docs/superpowers/plans/2026-08-20-phase-1-domain-storage.md`, partindo do checkpoint `f8f9fdd`.
- Bloqueios: nenhum.

## Progresso por fase

| Fase | Estado | Evidência / próximo marco |
|---|---|---|
| 0 — Bootstrap e decisões arquiteturais | Concluída | Integrada em `main`; 23 testes, 91,35% de branch coverage, Ruff, mypy, build e auditoria de dependências aprovados. |
| 1 — Domain model + storage | Em andamento | Tasks 1–4 aprovadas; Task 5 (projeto persistente e gate integrado) é o próximo marco. |
| 2 — Chemistry + Identity Resolver | Pendente | Aguardar gate Terra da Fase 1. |
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

Fase 0, em 2026-08-20:

- `pytest`: 23 testes aprovados;
- cobertura de branches: 91,35%;
- Ruff e mypy: aprovados;
- `uv lock`, build e `pip check`: aprovados;
- `pip-audit`: nenhuma vulnerabilidade conhecida nas dependências;
- CLI: ambas as entradas retornam a versão `0.1.0`.

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

## Convenções de continuidade

- Implementar cada comportamento por TDD: RED, GREEN e refatoração.
- Manter escritores em série quando houver sobreposição de arquivos.
- Executar revisão independente por tarefa e gate Terra ao fim de cada fase.
- Registrar aqui commit, testes, pendências e a próxima ação antes de qualquer pausa.
- Neste workspace OneDrive, usar `UV_LINK_MODE=copy` em sincronização e build para evitar problemas com reparse points da `.venv`.
