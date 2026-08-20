# FideliChem — Estado da implementação

Este documento é o checkpoint permanente da execução de `FideliChem_PLANO_CODEX.md`.
Atualize-o ao concluir cada tarefa ou sempre que o trabalho precisar ser interrompido.

## Estado atual

- Branch de execução: `feat/fidelichem-mvp-phases-1-16`
- Base integrada: `main` em `3ad80bc`
- Fase ativa: **Fase 1 — Domain model + storage**
- Etapa ativa: plano TDD congelado; Task 1 — dependências e primitivas imutáveis
- Próxima ação exata: preparar o workspace SDD e delegar a Task 1 de `docs/superpowers/plans/2026-08-20-phase-1-domain-storage.md` a um implementador Luna xhigh.
- Bloqueios: nenhum.

## Progresso por fase

| Fase | Estado | Evidência / próximo marco |
|---|---|---|
| 0 — Bootstrap e decisões arquiteturais | Concluída | Integrada em `main`; 23 testes, 91,35% de branch coverage, Ruff, mypy, build e auditoria de dependências aprovados. |
| 1 — Domain model + storage | Em andamento | Exploração concluída; spec e plano TDD criados; Task 1 é o próximo marco. |
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

## Convenções de continuidade

- Implementar cada comportamento por TDD: RED, GREEN e refatoração.
- Manter escritores em série quando houver sobreposição de arquivos.
- Executar revisão independente por tarefa e gate Terra ao fim de cada fase.
- Registrar aqui commit, testes, pendências e a próxima ação antes de qualquer pausa.
- Neste workspace OneDrive, usar `UV_LINK_MODE=copy` em sincronização e build para evitar problemas com reparse points da `.venv`.
