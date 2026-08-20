# Relatório da onda final de correções — Fase 0

- Base: `4a8ba04c85e5189a71c40318e81848c02aed6c9f`
- Commit de implementação: `a8df2d6` (`fix: close phase zero review findings`)
- Escopo: somente logging, aplicação GUI, testes diretamente relacionados e CI.

## Achados e correções

### 1. Formatter perdido em handler reutilizado

`configure_logging()` identificava corretamente o handler `fidelichem.console`,
mas só configurava o formatter ao criar um handler novo. A chamada a
`handler.setFormatter(logging.Formatter(_FORMAT))` foi movida para depois da
seleção/limpeza dos handlers, portanto toda chamada restaura o formatter
esperado sem alterar a política de handlers duplicados.

Regressão adicionada em
`tests/unit/test_logging.py::test_configure_logging_restores_formatter_on_reused_handler`:
um handler nomeado pré-existente sem formatter deve sair com o formato
`%(asctime)s %(levelname)s %(name)s: %(message)s`.

### 2. Falha GUI invisível no launcher Windows

`main()` continua preservando o traceback via `failure_logger.exception()` e
retornando `1`. Quando `QApplication.instance()` é uma QApplication real, a
falha também exibe uma mensagem genérica e segura através de
`QMessageBox.critical(None, "FideliChem", "FideliChem could not start. Please check the log for details.")`.
Detalhes da exceção não são enviados à UI; ficam apenas no log. Ausência de
QApplication, ou presença de apenas um QCoreApplication incompatível, não
tenta abrir modal.

O teste GUI substitui `QMessageBox.critical` somente no teste para capturar a
mensagem sem bloquear o runner; não foi adicionado hook de teste à produção.
Também foi adicionada proteção de configuração que lê o entry point instalado
`fidelichem-gui`, exige
`fidelichem.gui.application:main` e verifica que o alvo é importável/callable.

### 3. Actions CI mutáveis

`.github/workflows/ci.yml` agora mantém comentários de tags legíveis, mas usa
somente os SHAs oficiais imutáveis:

- `actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4`
- `actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5`
- `astral-sh/setup-uv@d0d8abe699bfb85fec6de9f7adb5ae17292296ff # v6`

O check de configuração exige cada combinação SHA/comentário e rejeita o
formato mutável `@v4`/`@v5`/`@v6`.

## Evidência RED/GREEN e mutation

Antes da produção ser alterada, o teste focado novo foi executado e falhou em
três casos: formatter reutilizado (`assert None is not None`), mensagem GUI não
capturada (`KeyError: 'parent'`) e actions sem SHA esperado (`AssertionError`).
Após a implementação:

```text
4 passed in 0.11s
All checks passed!  (Ruff nos arquivos alterados)
```

Para contratos já existentes, foram feitas mutações temporárias honestas e
revertidas imediatamente:

- `handler.setLevel(resolved_level)` → `logging.DEBUG`: o teste de idempotência
  falhou com `assert 10 == 20`.
- `return 1` no caminho de falha GUI → `return 0`: o teste de startup falhou
  com `assert 0 == 1`.

## Verificação completa

Todos os comandos abaixo terminaram com código 0:

```text
uv lock --check
uv run ruff check .                         All checks passed!
uv run mypy src/fidelichem                 Success: no issues found in 8 source files
uv run pip-audit                            No known vulnerabilities found
$env:QT_QPA_PLATFORM='offscreen'; uv run pytest --cov=fidelichem --cov-branch --cov-report=term-missing --cov-fail-under=80
                                             23 passed; 91.35% branch coverage
uv run fidelichem --version                 fidelichem 0.1.0
uv run python -m fidelichem --version       fidelichem 0.1.0
uv pip check                                All installed packages are compatible
git diff --check                            clean
```

`uv build` inicialmente encontrou OS error 396 ao criar hardlinks dentro do
OneDrive. A mitigação indicada pelo próprio uv foi usada sem alterar o projeto:

```text
$env:UV_LINK_MODE='copy'; uv build
Successfully built dist\fidelichem-0.1.0.tar.gz
Successfully built dist\fidelichem-0.1.0-py3-none-any.whl
```

## Self-review

- A mudança de logging é idempotente e cobre handler novo, reutilizado e
  duplicado; nenhum dado científico é envolvido.
- O texto mostrado ao usuário é constante e genérico; o traceback permanece no
  logger operacional. O modal real é deliberadamente visível no launcher, e o
  teste o intercepta sem bloquear.
- A guarda `isinstance(application, QApplication)` evita invocar widgets com
  um aplicativo Qt incompatível.
- O entry point foi verificado pela metadata instalada e pelo alvo importável.
- O workflow não mantém referências `uses: ...@vN`; cada SHA e comentário foi
  validado por teste de configuração.
- Nenhuma dependência, documentação de produto ou arquivo de terceiro foi
  alterado; este relatório é o único artefato documental novo solicitado.
- A execução remota do GitHub Actions não foi possível observar localmente;
  a estrutura e os pinos estão cobertos pelo check de configuração.
