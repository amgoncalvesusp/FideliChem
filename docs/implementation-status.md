# FideliChem — Estado da implementação

Este documento é o checkpoint permanente da execução de `FideliChem_PLANO_CODEX.md`.
Atualize-o ao concluir cada tarefa ou sempre que o trabalho precisar ser interrompido.

## Estado atual

- Branch de execução: `feat/fidelichem-mvp-phases-1-16`
- Base integrada: `main` em `3ad80bc`
- Fase ativa: **Fase 1 — Domain model + storage**
- Etapa ativa: exploração paralela e consolidação do desenho técnico
- Próxima ação exata: consolidar o modelo relacional, os riscos de migration/provenance e as invariantes de banco em uma especificação e um plano TDD da Fase 1.
- Bloqueios: nenhum.

## Progresso por fase

| Fase | Estado | Evidência / próximo marco |
|---|---|---|
| 0 — Bootstrap e decisões arquiteturais | Concluída | Integrada em `main`; 23 testes, 91,35% de branch coverage, Ruff, mypy, build e auditoria de dependências aprovados. |
| 1 — Domain model + storage | Em andamento | Exploração, especificação e plano TDD. |
| 2 — Chemistry + Identity Resolver | Pendente | Aguardar gate Terra da Fase 1. |
| 3 — Adapter SDK + Import Manager | Pendente | Aguardar gate Terra da Fase 2. |
| 4 — Universal Table Importer | Pendente | Aguardar gate Terra da Fase 3. |
| 5 — Score Registry + normalization | Pendente | Aguardar gate Terra da Fase 4. |
| 6 — GOLD Adapter | Pendente | Aguardar gate Terra da Fase 5. |
| 7 — SMILES2Select + SMILES2Docking | Pendente | Aguardar gate Terra da Fase 6. |
| 8 — DockLens | Pendente | Aguardar gate Terra da Fase 7. |
| 9 — MolDynStudio + GROMACS | Pendente | Aguardar gate Terra da Fase 8. |
| 10 — Analytics Engine | Pendente | Aguardar gate Terra da Fase 9. |
| 11 — Decision Engine | Pendente | Aguardar gate Terra da Fase 10. |
| 12 — GUI | Pendente | Aguardar gate Terra da Fase 11. |
| 13 — Export + reproducibility | Pendente | Aguardar gate Terra da Fase 12. |
| 14 — Performance + hardening | Pendente | Aguardar gate Terra da Fase 13. |
| 15 — Packaging + release candidate | Pendente | Aguardar gate Terra da Fase 14. |
| 16 — Final audit | Pendente | Aguardar gate Terra da Fase 15. |

## Último gate verificado

Fase 0, em 2026-08-20:

- `pytest`: 23 testes aprovados;
- cobertura de branches: 91,35%;
- Ruff e mypy: aprovados;
- `uv lock`, build e `pip check`: aprovados;
- `pip-audit`: nenhuma vulnerabilidade conhecida nas dependências;
- CLI: ambas as entradas retornam a versão `0.1.0`.

## Convenções de continuidade

- Implementar cada comportamento por TDD: RED, GREEN e refatoração.
- Manter escritores em série quando houver sobreposição de arquivos.
- Executar revisão independente por tarefa e gate Terra ao fim de cada fase.
- Registrar aqui commit, testes, pendências e a próxima ação antes de qualquer pausa.
- Neste workspace OneDrive, usar `UV_LINK_MODE=copy` em sincronização e build para evitar problemas com reparse points da `.venv`.
