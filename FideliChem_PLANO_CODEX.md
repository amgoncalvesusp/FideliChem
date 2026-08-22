# FideliChem — Plano de Implementação no Codex

> Estado de execução: consulte [docs/implementation-status.md](docs/implementation-status.md). Esse registro é atualizado e versionado a cada checkpoint para permitir retomada exata entre sessões.

**Nome de trabalho:** FideliChem  
**Subtítulo:** Explainable Multi-Fidelity Molecular Evidence & Decision Platform  
**Objetivo deste documento:** permitir que outra IA, trabalhando no Codex, implemente o software de forma incremental, testável e economicamente eficiente, usando subagents — preferencialmente **GPT-5.6 Luna com raciocínio `xhigh` (Extra High)** — para tarefas bem delimitadas.

---

## 0. Instrução principal para o agente que receber este plano

Você está construindo um software científico. **Não implemente tudo de uma vez.**

Trabalhe fase por fase, respeitando as dependências, critérios de aceite e contratos de dados definidos neste documento.

Regras obrigatórias:

1. Antes de alterar código existente, inspecione o repositório e os testes.
2. Em cada fase, delegue tarefas independentes a subagents.
3. Use **GPT-5.6 Luna + `xhigh`** como padrão para exploração, adapters, testes, documentação, parsing, refactors locais e implementações bem especificadas.
4. Use **GPT-5.6 Terra + `xhigh`** apenas para revisão de integração, decisões arquiteturais de médio risco, depuração transversal ou quando dois subagents Luna discordarem.
5. Use **GPT-5.6 Sol + `xhigh` ou `max` somente excepcionalmente**, para:
   - decisões arquiteturais irreversíveis;
   - problemas científicos/estatísticos de alta complexidade;
   - bugs de integração persistentes após duas tentativas independentes;
   - revisão final de um release importante.
6. Não faça vários subagents escreverem simultaneamente nos mesmos arquivos.
7. Prefira paralelizar **leitura, exploração, testes, revisão e desenho de adapters**.
8. Faça integração de código de forma serial.
9. Após cada fase:
   - rode todos os testes;
   - registre decisões;
   - atualize documentação;
   - gere um resumo do que foi implementado;
   - somente avance se os critérios de aceite estiverem satisfeitos.
10. Não introduza machine learning antes de concluir o núcleo de evidências, identidade molecular, adapters e decisão determinística.
11. Não copie código dos outros projetos do autor sem revisar compatibilidade de licença. Integre por **formatos, contratos, arquivos e APIs**, não por cópia indiscriminada.
12. Não empacote nem distribua executáveis proprietários de terceiros, como GOLD. O FideliChem deve apenas interpretar arquivos produzidos pelo usuário.

---

# 1. Visão do produto

O FideliChem deve ser uma plataforma desktop para **reunir, normalizar, auditar, comparar e priorizar evidências moleculares oriundas de diferentes programas científicos**.

A arquitetura não deve depender de nenhum software específico.

O princípio é:

> **O FideliChem não entende programas como entidades centrais; ele entende moléculas, estados moleculares, alvos, poses, scores, interações, simulações, métricas e evidências.**

Programas diferentes são apenas produtores de evidência.

Exemplos de fontes:

- SMILES2Select
- SMILES2Docking
- GOLD
- AutoDock Vina
- GNINA
- DockLens
- MolDynStudio
- GROMACS
- planilhas CSV/XLSX
- dados experimentais
- futuramente Glide, PLANTS, DOCK, OpenFE, FEP etc.

---

# 2. Problema científico que o software deve resolver

Em uma campanha típica, um mesmo composto pode passar por:

1. seleção de drug-likeness;
2. preparação estrutural;
3. docking;
4. rescoring;
5. análise de interações;
6. dinâmica molecular;
7. ensaio experimental.

Esses resultados normalmente permanecem separados por programa.

O FideliChem deve transformar isto:

```text
SMILES2Select -> arquivo A
GOLD          -> pasta B
DockLens      -> arquivo C
MolDynStudio  -> pasta D
Experimento   -> planilha E
```

nisto:

```text
CMPD000143
├── identidade química
├── estados moleculares
├── propriedades e filtros
├── docking
│   ├── execução 1
│   ├── execução 2
│   └── múltiplas funções de pontuação
├── poses
├── interações
├── dinâmica molecular
├── métricas
└── evidência experimental
```

A unidade central do sistema passa a ser **a molécula**, e não o software que gerou o arquivo.

---

# 3. Escopo do MVP

## 3.1 Deve existir no MVP

### Núcleo
- projeto FideliChem;
- banco de evidências;
- provenance/auditoria;
- sistema de identidade molecular;
- adapters independentes;
- importação incremental;
- rollback de importação;
- QC de importação;
- normalização de scores;
- consenso de rankings;
- Pareto;
- decisão multicritério explicável;
- exportação de tabelas e relatório de métodos.

### Adapters prioritários
1. Generic Table Importer
2. SMILES2Select
3. GOLD
4. DockLens
5. MolDynStudio
6. GROMACS analítico
7. SMILES2Docking como provenance/estado estrutural

### Interface
- criação/abertura de projeto;
- import wizard;
- tabela de compostos;
- painel de evidências;
- painel de QC;
- comparação de scores;
- decisão/priorização;
- exportação.

## 3.2 Não implementar no primeiro MVP

- FEP;
- geração molecular;
- treinamento de deep learning;
- active learning;
- execução automática de docking;
- execução automática de MD;
- análise direta completa de XTC/TRR;
- servidor web;
- colaboração em nuvem;
- banco remoto;
- LLM dentro do aplicativo;
- "AI score" opaco.

Esses itens devem ficar previstos na arquitetura, mas fora do release inicial.

---

# 4. Arquitetura conceitual

```text
                    ┌──────────────────────────────┐
                    │        FideliChem UI         │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │        Import Manager        │
                    └──────────────┬───────────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       │                           │                           │
       ▼                           ▼                           ▼
Native adapters              Known formats                User mapping
GOLD                         MOL2 / SDF                  CSV / TSV
SMILES2Select                PDB / PDBQT                XLS / XLSX
DockLens                     JSON                       Parquet
MolDynStudio                 XVG                        JSON/JSONL
GROMACS
       │                           │                           │
       └───────────────────────────┴───────────────────────────┘
                                   │
                          Canonical Import Bundle
                                   │
                    ┌──────────────▼───────────────┐
                    │      Identity Resolver       │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │ Canonical Molecular Evidence│
                    │          Database            │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
       QC / Provenance       Analytics Engine      Decision Engine
              │                    │                    │
              └────────────────────┴────────────────────┘
                                   │
                           Next Best Evidence
                           (versão futura)
```

---

# 5. Stack tecnológica recomendada

## 5.1 Linguagem

- Python 3.11 ou 3.12.

Escolher uma versão e fixá-la no projeto.

## 5.2 GUI

- **PySide6**.

Motivos:
- Qt moderno;
- boa experiência desktop;
- model/view adequado para tabelas grandes;
- licenciamento mais conveniente que copiar implementações de outros projetos;
- possibilidade de empacotamento Windows/Linux.

## 5.3 Química

- RDKit.

Usos:
- canonical SMILES;
- InChI/InChIKey quando disponível;
- fingerprints;
- scaffolds;
- atom mapping;
- RMSD de poses;
- normalização estrutural.

O RDKit deve ficar atrás de um módulo de serviço, para não espalhar chamadas por toda a aplicação.

## 5.4 Validação de modelos

- Pydantic v2.

## 5.5 Persistência

Recomendação:

- **SQLite** como banco canônico do projeto;
- SQLAlchemy 2.x para persistência/migrations;
- Alembic para versionamento de schema;
- Parquet para exportação e grandes tabelas analíticas;
- Pandas/Polars somente nas bordas e analytics, nunca como banco principal.

## 5.6 Estatística

- NumPy
- SciPy
- pandas ou Polars
- scikit-learn somente quando necessário para clustering/normalização auxiliar.

## 5.7 Gráficos

MVP:
- PyQtGraph para gráficos interativos rápidos;
- Matplotlib para exportação publication-ready.

## 5.8 Testes

- pytest
- pytest-qt
- hypothesis para casos de parsing/identity quando adequado
- coverage

## 5.9 Empacotamento

- PyInstaller;
- Windows x64;
- Ubuntu x64;
- GitHub Actions para builds e testes.

---

# 6. Estrutura de diretórios

```text
FideliChem/
├── AGENTS.md
├── README.md
├── CHANGELOG.md
├── CITATION.cff
├── LICENSE
├── pyproject.toml
├── uv.lock / requirements lock
├── .codex/
│   ├── config.toml
│   └── agents/
│       ├── luna-explorer.toml
│       ├── luna-worker.toml
│       ├── luna-adapter.toml
│       ├── luna-tests.toml
│       ├── luna-docs.toml
│       ├── terra-reviewer.toml
│       └── sol-architect.toml
├── src/
│   └── fidelichem/
│       ├── app/
│       ├── domain/
│       ├── chemistry/
│       ├── adapters/
│       │   ├── base/
│       │   ├── generic_table/
│       │   ├── smiles2select/
│       │   ├── smiles2docking/
│       │   ├── gold/
│       │   ├── docklens/
│       │   ├── moldynstudio/
│       │   └── gromacs/
│       ├── identity/
│       ├── importers/
│       ├── storage/
│       ├── analytics/
│       ├── decision/
│       ├── provenance/
│       ├── export/
│       ├── gui/
│       └── cli/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── adapters/
│   ├── fixtures/
│   └── golden/
├── docs/
│   ├── architecture/
│   ├── adapters/
│   ├── methods/
│   └── decisions/
└── scripts/
```

---

# 7. Modelo de domínio

Não permitir que cada adapter crie sua própria estrutura improvisada.

Todo adapter deve produzir objetos canônicos.

## 7.1 Entidades principais

### Project

```text
Project
- id
- name
- description
- created_at
- updated_at
- schema_version
```

### Target

```text
Target
- id
- project_id
- name
- accession
- pdb_id
- chain
- sequence_hash
- notes
```

### Compound

Representa a entidade química principal.

```text
Compound
- id                # FideliChem internal ID
- canonical_smiles
- isomeric_smiles
- inchikey
- formula
- molecular_weight
- structure_hash
- created_at
```

### MolecularState

Docking deve pertencer a um **estado molecular**, não apenas ao Compound.

```text
MolecularState
- id
- compound_id
- state_smiles
- state_inchikey
- formal_charge
- stereochemistry_signature
- protonation_signature
- tautomer_signature
- state_hash
- preparation_ph
```

A mesma molécula pode ter:

```text
CMPD001
├── STATE001  protonada em pH 7,4
├── STATE002  tautômero B
└── STATE003  forma neutra
```

### Alias

```text
Alias
- id
- compound_id
- molecular_state_id optional
- source_system
- source_value
- import_batch_id
```

Exemplo:

```text
FideliChem        CMPD000143
SMILES2Select     ZINC000123
GOLD              ligand_00457
DockLens          ligand_00457
GROMACS           LIG
```

### ImportBatch

Cada importação precisa ser reversível.

```text
ImportBatch
- id
- adapter_id
- adapter_version
- started_at
- completed_at
- status
- source_root
- file_count
- input_hash
- warnings
```

### SourceArtifact

```text
SourceArtifact
- id
- import_batch_id
- path
- relative_path
- sha256
- file_type
- size_bytes
- mtime
```

### DockingRun

```text
DockingRun
- id
- target_id
- import_batch_id
- engine
- engine_version
- configuration_hash
- run_name
- run_parameters_json
```

### Pose

```text
Pose
- id
- docking_run_id
- molecular_state_id
- source_pose_id
- rank
- structure_artifact_id
- coordinate_hash
```

### ScoreDefinition

Essencial para não misturar escalas diferentes.

```text
ScoreDefinition
- id
- key
- display_name
- domain
- source_engine
- direction
    higher_better
    lower_better
    target_range
    descriptive
- unit
- comparability_scope
- description
```

Exemplos:

```text
gold.chemplp
gold.goldscore
gold.chemscore
gold.asp
vina.affinity
gnina.cnn_score
```

### ScoreObservation

```text
ScoreObservation
- id
- pose_id
- score_definition_id
- raw_value
- normalized_value nullable
- percentile nullable
- source_artifact_id
```

### InteractionObservation

```text
InteractionObservation
- id
- target_id
- pose_id nullable
- md_run_id nullable
- residue_id
- interaction_type
- ligand_atom
- receptor_atom
- distance
- angle
- occupancy
- source_profile
- source_system
```

### MDRun

```text
MDRun
- id
- target_id
- molecular_state_id
- import_batch_id
- engine
- engine_version
- duration_ns
- temperature_k
- pressure_bar
- timestep_fs
- frame_interval_ps
- replicas
- parameters_json
```

### MetricDefinition

```text
MetricDefinition
- key
- display_name
- domain
- unit
- direction
- aggregation
```

### MetricObservation

```text
MetricObservation
- id
- md_run_id nullable
- compound_id nullable
- pose_id nullable
- metric_definition_id
- value
- uncertainty
- aggregation
- source_artifact_id
```

### ExperimentalObservation

Preparar agora, mesmo sem usar em toda campanha.

```text
ExperimentalObservation
- id
- compound_id
- target_id
- assay_type
- endpoint
- value
- unit
- qualifier
- conditions_json
- source
```

---

# 8. Contrato universal de adapter

O Adapter Layer é a parte mais importante da arquitetura.

## 8.1 Princípio

**Nenhum adapter escreve diretamente no banco.**

Ele apenas:

1. detecta;
2. planeja;
3. interpreta;
4. valida;
5. devolve um `ImportBundle`.

O Import Manager é o único componente autorizado a persistir.

## 8.2 Interface sugerida

```python
class EvidenceAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def probe(self, source: Path) -> DetectionReport: ...

    def plan(self, source: Path, options: dict) -> ImportPlan: ...

    def parse(self, plan: ImportPlan) -> ImportBundle: ...

    def validate(self, bundle: ImportBundle) -> ValidationReport: ...
```

## 8.3 DetectionReport

```text
confidence
detected_format
candidate_files
warnings
requires_user_mapping
suggested_adapter
```

## 8.4 ImportPlan

Imutável.

```text
source files
hashes
adapter
options
mappings
target
run grouping
identity strategy
```

## 8.5 ImportBundle

Deve conter somente dados canônicos:

```text
targets
compounds
molecular_states
aliases
docking_runs
poses
scores
interactions
md_runs
metrics
experimental_observations
source_artifacts
qc_messages
provenance
```

## 8.6 Plugin architecture futura

Preparar entry points:

```toml
[project.entry-points."fidelichem.adapters"]
my_adapter = "package.module:Adapter"
```

Assim terceiros poderão instalar novos adapters sem alterar o core.

---

# 9. Níveis de compatibilidade

## Tier 1 — Native Adapter

O FideliChem conhece a semântica do programa.

Prioridade MVP:

- SMILES2Select
- GOLD
- DockLens
- MolDynStudio
- SMILES2Docking
- GROMACS analysis output

## Tier 2 — Known Format

Conhece o formato, mas não o programa.

- MOL2
- SDF
- PDB
- PDBQT
- XVG
- JSON
- Parquet

## Tier 3 — User Mapping

Para qualquer tabela:

- CSV
- TSV
- XLS/XLSX
- Parquet
- JSON/JSONL

O usuário mapeia colunas e salva um preset.

---

# 10. Identity Resolver

Esta parte é crítica.

## 10.1 Nunca confiar apenas no nome do ligante

Exemplo:

```text
SMILES2Select: ZINC000123
GOLD:          ligand_457
DockLens:      ligand_457
GROMACS:       LIG
```

Podem ser a mesma molécula.

## 10.2 Ordem de resolução

### Nível 1 — identidade química exata

Quando existe estrutura química confiável:

1. canonical isomeric SMILES;
2. InChIKey;
3. structure hash.

### Nível 2 — molecular state

Diferenciar:

- carga;
- tautômero;
- estereoquímica;
- protômero.

### Nível 3 — aliases

Usar nomes apenas como evidência auxiliar.

### Nível 4 — confirmação humana

Se houver ambiguidade:

```text
Possível correspondência:
GOLD ligand_457

Candidate A: CMPD000143
Candidate B: CMPD000901

[Associar A] [Associar B] [Criar novo]
```

## 10.3 Não fazer merge silencioso

Toda fusão ambígua deve:
- solicitar confirmação;
- ficar registrada no audit log;
- ser reversível.

---

# 11. Provenance e reprodutibilidade

Cada dado deve responder:

> De onde veio este número?

Guardar:

- programa;
- versão;
- adapter;
- versão do adapter;
- arquivo;
- SHA-256;
- data de importação;
- linha/bloco original quando aplicável;
- parâmetros do run;
- transformação aplicada;
- política de normalização;
- política de decisão.

Nunca sobrescrever o valor bruto.

---

# 12. Adapter GOLD — prioridade máxima

O GOLD deve ser tratado como integração de primeira classe.

## 12.1 Entrada

Suportar:

### Pasta completa de docking

Detectar arquivos conhecidos, por exemplo:

```text
gold.conf
gold.log
bestranking.lst
gold_soln_*.mol2
ranked_*.mol2
```

Não depender de todos existirem.

### Arquivos individuais

O usuário também deve conseguir selecionar:
- um ou vários MOL2;
- ranking lists;
- arquivos de rescoring;
- múltiplas pastas/runs.

## 12.2 Funções de pontuação

Tratar separadamente:

- ChemPLP
- GoldScore
- ChemScore
- ASP

Se houver rescoring adicional, registrar como observação distinta.

**Nunca calcular média dos valores brutos.**

## 12.3 Direção

O registry de métricas deve declarar explicitamente:

```text
GOLD scoring functions -> higher_better
```

Mas preservar o valor original.

## 12.4 Multiple scoring functions

Uma pose pode ter:

```text
Pose P001
ChemPLP       86.4
GoldScore     72.1
ChemScore     41.8
ASP           45.0
```

Esses valores pertencem à pose e ao run.

## 12.5 Múltiplos dockings da mesma proteína

Suportar:

```text
Target CTX-M-15
├── Run GOLD_01
│   └── ChemPLP
└── Run GOLD_02
    └── GoldScore
```

ou:

```text
Run GOLD_03
└── mesmo conjunto de poses
    ├── ChemPLP
    ├── GoldScore
    ├── ChemScore
    └── ASP
```

Não colapsar runs distintos.

## 12.6 Poses

Cada pose deve possuir:
- run;
- molécula/estado;
- pose source ID;
- rank;
- arquivo original;
- coordinate hash;
- scores associados.

## 12.7 QC GOLD

Detectar:
- ligante sem score;
- score sem pose;
- pose duplicada;
- arquivo truncado;
- ligand ID inconsistente;
- número de poses diferente do ranking;
- scoring function desconhecida;
- arquivos de runs diferentes misturados;
- ausência de identificação de receptor/target.

## 12.8 Fixture-driven development

Não implementar parser GOLD apenas por suposição.

Criar fixtures com:
- pelo menos 2 ligantes;
- pelo menos 3 poses por ligante;
- mais de uma scoring function;
- um arquivo incompleto;
- um ID repetido;
- um caso de rescoring.

Se arquivos reais estiverem disponíveis durante a implementação, criar golden tests a partir deles, removendo dados sensíveis quando necessário.

---

# 13. Adapter SMILES2Select

## Prioridade de leitura

1. SQLite da execução, se disponível;
2. XLSX;
3. Parquet;
4. CSV/TSV.

Importar:

- original ID;
- canonical SMILES;
- selected/excluded;
- perfil de regras;
- QED;
- SA score;
- alertas;
- scaffold;
- descritores presentes;
- motivo da decisão;
- run configuration quando disponível.

Não transformar "selected" em verdade absoluta.

Registrar como:

```text
evidence:
    source = SMILES2Select
    category = selection
    decision = selected
```

O Decision Engine do FideliChem continua independente.

---

# 14. Adapter SMILES2Docking

O SMILES2Docking não é principalmente uma fonte de afinidade, mas uma fonte importante de:

- identidade;
- molecular state;
- protonação;
- tautomeria;
- geometria 3D;
- provenance de preparação.

Importar, quando disponível:

- ID;
- SMILES inicial;
- canonical SMILES;
- estado protonado;
- pH;
- backend de protonação;
- tautômero;
- método de otimização;
- MOPAC status/method;
- arquivo estrutural gerado;
- hash do arquivo;
- run JSON.

Não criar score de "qualidade" artificial.

---

# 15. Adapter DockLens

O DockLens deve fornecer evidência mecanística.

Preferência:

1. formato estruturado estável/export JSON, se disponível;
2. CSV/XLSX exportado;
3. projeto `.docklens` somente quando o schema estiver documentado e versionado.

Importar:

- pose/source ID;
- source file;
- target;
- interação;
- resíduo;
- tipo;
- distância;
- ângulo;
- perfil científico;
- frequência/occupancy;
- fingerprints;
- state/family quando aplicável;
- retenção docking -> MD quando presente.

## Regra importante

DockLens deve ser associado à **pose** ou ao **MD run** correspondente.

Não armazenar tudo apenas no Compound.

## Interaction key

Sugestão:

```text
target | residue | interaction_type | ligand_feature
```

Permitir versão menos granular:

```text
target | residue | interaction_type
```

para consenso.

---

# 16. Adapter MolDynStudio

O MVP deve tratar MolDynStudio como fonte estruturada de resultados.

Importar:
- informações da simulação;
- duração;
- temperatura;
- timestep;
- trajetória;
- métricas produzidas;
- arquivos analíticos;
- configuração;
- associação com molécula/target.

Se o MolDynStudio ainda não possuir um manifest estável, implementar inicialmente adapter de seus arquivos tabulares/relatórios.

Em paralelo, documentar uma proposta opcional de export:

```text
fidelichem-md-result-v1.json
```

Isso melhora integração futura, mas FideliChem **não deve depender** desse manifest.

---

# 17. Adapter GROMACS — MVP analítico

Não começar pela leitura direta de trajetórias.

Suportar resultados já calculados:

```text
*.xvg
*.csv
*.dat
*.json
```

Exemplos:

- RMSD
- RMSF
- radius of gyration
- SASA
- H-bonds
- distances
- energy terms

## XVG Parser

Precisa:
- preservar metadata;
- ignorar comentários corretamente;
- ler legends;
- identificar unidades;
- aceitar múltiplas séries;
- não assumir que coluna 2 é sempre a métrica desejada.

## Fase futura

Entrada:

```text
TPR/GRO/PDB + XTC/TRR
```

para análise direta.

Não fazer no MVP.

---

# 18. Universal Table Importer

Este é o mecanismo que torna o FideliChem independente dos programas suportados.

## Formatos

- CSV
- TSV
- XLS
- XLSX
- Parquet
- JSON
- JSONL

## Wizard

### Passo 1
Escolher arquivo/sheet.

### Passo 2
Preview.

### Passo 3
Mapear identidade:

```text
Molecule ID  -> coluna
SMILES       -> coluna
InChIKey     -> coluna
Target       -> coluna
Pose ID      -> coluna
Run ID       -> coluna
```

### Passo 4
Mapear evidências.

Exemplo:

```text
DockingScore
type      = score
direction = lower_better
unit      = none
scope     = run
```

### Passo 5
Salvar preset.

Exemplo:

```text
generic-presets/
└── my_lab_docking_v2.json
```

O preset deve poder ser usado em outro arquivo com mesmas colunas.

## Requisito

Importar tabela desconhecida não pode exigir alteração de código.

---

# 19. Score Registry e normalização

Princípio científico central:

> Scores de métodos diferentes não devem ser somados diretamente em escala bruta.

Exemplo inválido:

```text
ChemPLP 84.3 + Vina -9.2 + GoldScore 67.5
```

## 19.1 Manter três camadas

### Raw

```text
raw_value
```

imutável.

### Relative / normalized

Dentro de um escopo declarado:

```text
percentile
rank
robust_z
```

### Calibrated

Futuro, quando houver dados experimentais.

```text
predicted probability
calibration model
uncertainty
```

## 19.2 Escopo

Percentis devem ser calculados dentro de:

```text
target
+ docking_run
+ score_definition
```

Nunca comparar percentil de runs incompatíveis sem declarar a transformação.

## 19.3 Default do MVP

Usar **percentile rank orientado para "melhor = 1"**.

Assim:

```text
ChemPLP higher_better:
raw 90 -> percentile 0.97

Vina lower_better:
raw -10 -> percentile 0.96
```

Os raws continuam intactos.

---

# 20. Analytics Engine — MVP

## 20.1 Score Consensus

Calcular:

- percentile por score;
- rank;
- mediana dos percentis;
- média ponderada opcional;
- dispersão dos ranks;
- quantidade de métodos disponíveis.

Não exigir que todos os compostos tenham todos os scores.

## 20.2 Score Agreement

Por campanha:
- Spearman entre funções;
- Kendall opcional;
- matriz de correlação;
- concordância top-k.

Por molécula:
- amplitude de percentis;
- desvio dos percentis;
- classificação:
  - HIGH
  - MODERATE
  - LOW

Limites devem ser configuráveis e descritos no relatório.

## 20.3 Pareto

Eixos configuráveis:

```text
docking consensus
drug-likeness
synthetic accessibility
interaction evidence
MD stability
```

Não reduzir Pareto a um único score.

## 20.4 Pose Consensus

Quando houver coordenadas comparáveis:

1. atom mapping;
2. heavy atom RMSD;
3. matriz de RMSD;
4. clustering;
5. medoid;
6. estabilidade da família.

Resultado:

```text
HIGH / MODERATE / LOW
```

com valores quantitativos.

## 20.5 Interaction Consensus

Comparar interações entre poses/runs:

```text
SER70 hbond     4/5 poses
GLU166 hbond    5/5 poses
TYR105 pi       2/5 poses
```

## 20.6 Dynamic Evidence

No MVP, apenas resultados importados.

Exemplo:

```text
ligand RMSD
protein RMSD
H-bond occupancy
contact retention
SASA
Rg
distance metric
```

Não criar uma regra universal de "estável" sem configuração.

---

# 21. Decision Engine — v0.1

O FideliChem deve ser **explicável**.

Não criar `AI_SCORE`.

## 21.1 Decision Profile

JSON/YAML versionado:

```yaml
name: beta_lactamase_default
version: 1

criteria:
  docking_consensus:
    role: rank
    weight: 1.0

  key_interactions:
    role: rank
    weight: 1.0

  md_contact_retention:
    role: rank
    weight: 1.0

  pains:
    role: warning

  synthetic_accessibility:
    role: rank
    weight: 0.5
```

## 21.2 Tipos de papel

- mandatory
- exclusion
- rank
- warning
- informative

## 21.3 Saída

Para cada molécula:

```text
Priority: ADVANCE

Why:
+ top 5% ChemPLP
+ top 8% GoldScore
+ high cross-score agreement
+ SER70 H-bond in 90% of analyzed poses
+ GLU166 interaction preserved
+ MD contact retention 82%

Warnings:
- SA score 5.4
```

ou:

```text
Priority: HOLD

Why:
+ strong docking score
- low pose consensus
- key interaction not reproducible
- no MD evidence

Recommended next evidence:
DockLens analysis or short MD
```

A recomendação "next evidence" no MVP pode ser baseada em regras, não IA.

---

# 22. Next Best Evidence — versão posterior

Após o MVP, implementar:

```text
Compound -> qual evidência falta e tem maior valor?
```

Possíveis ações:

- obter outra scoring function;
- rescore;
- analisar no DockLens;
- executar MD curta;
- testar outro estado de protonação;
- obter dado experimental;
- não investir mais.

Somente depois introduzir:
- active learning;
- uncertainty;
- expected information gain;
- custo computacional;
- multi-fidelity optimization.

---

# 23. GUI

## 23.1 Janela principal

Sidebar:

```text
Project
Import
Compounds
Docking
Interactions
Dynamics
Decision
QC
Exports
Settings
```

## 23.2 Import

Mostrar:

```text
Detected:
GOLD docking folder

12 ligands
120 poses
Scoring: ChemPLP
Additional rescoring: GoldScore, ChemScore
Warnings: 1
```

Antes de persistir.

## 23.3 Compound Explorer

Painel esquerdo:
- tabela de moléculas;
- busca;
- filtros.

Painel central:
- 2D structure;
- aliases;
- states.

Painel direito:
- evidence summary.

Tabs:

```text
Chemistry
Docking
Poses
Interactions
MD
Experimental
Provenance
```

## 23.4 Decision

Tabela:

```text
Compound
Docking consensus
Score agreement
Pose consensus
Interactions
MD evidence
Warnings
Priority
```

## 23.5 QC

QC não pode ficar escondido em logs.

Categorias:

- ERROR
- WARNING
- INFO

Filtros por:
- import batch;
- adapter;
- compound;
- file.

---

# 24. Project format

Estrutura recomendada:

```text
MyProject/
├── project.fidelichem.sqlite
├── project.json
├── artifacts/
├── cache/
├── exports/
└── logs/
```

Por padrão, não duplicar arquivos enormes.

Guardar:
- path;
- hash;
- metadata.

Oferecer opção:

```text
Make project portable
```

que copia os inputs necessários para `artifacts/`.

Futuramente permitir pacote:

```text
project.fidelichem
```

zipado/versionado.

---

# 25. Audit log

Toda alteração relevante:

```text
timestamp
action
entity
old_value
new_value
source
user/system
```

Exemplos:

- merge de aliases;
- mudança de target;
- override de identity;
- alteração de direction de score;
- aplicação de decision profile;
- exclusão de import batch.

---

# 26. Exportação

## CSV/XLSX

- compound summary;
- score matrix;
- pose matrix;
- interactions;
- MD metrics;
- decision;
- QC;
- provenance.

## Parquet

Para dados maiores.

## Reproducibility manifest

JSON:

```text
FideliChem version
schema version
adapter versions
input hashes
normalization policy
decision profile hash
software versions
timestamp
```

## Methods report

Gerar texto factual:

```text
Imported 4 GOLD docking runs...
Scores were converted to within-run oriented percentile ranks...
Raw scores were retained unchanged...
```

Nunca afirmar significância científica não calculada.

---

# 27. CLI

Mesmo com GUI, criar CLI desde cedo.

Exemplos:

```bash
fidelichem project create ./ctxm_project

fidelichem import gold ./gold_run \
    --project ./ctxm_project

fidelichem import generic results.xlsx \
    --preset presets/my_mapping.json \
    --project ./ctxm_project

fidelichem qc ./ctxm_project

fidelichem analyze consensus ./ctxm_project

fidelichem export xlsx ./ctxm_project output.xlsx
```

A GUI deve chamar os mesmos serviços do CLI.

Nunca implementar lógica científica somente na GUI.

---

# 28. Estratégia de testes

## 28.1 Regra

Cada adapter deve ter golden fixtures.

## 28.2 Unit tests

- identity;
- score direction;
- normalization;
- percentile;
- parsing;
- provenance;
- hashing;
- alias resolution;
- state separation.

## 28.3 Adapter contract tests

Todo adapter precisa passar pelo mesmo suite:

```text
probe
plan
parse
validate
determinism
idempotency
rollback
provenance
```

## 28.4 Integration tests

Pipelines:

```text
SMILES2Select -> GOLD -> DockLens
GOLD -> DockLens -> MD
Generic -> Decision
```

## 28.5 Idempotência

Importar o mesmo batch duas vezes:
- detectar duplicidade;
- não criar duplicatas silenciosas.

## 28.6 Database migration tests

Abrir projetos de schemas anteriores.

## 28.7 Scientific regression tests

Guardar pequenos casos conhecidos:

```text
ranking before normalization
ranking after normalization
expected percentile
expected consensus
expected Pareto membership
```

## 28.8 GUI

pytest-qt para:
- import wizard;
- tabelas;
- filters;
- background jobs;
- cancelamento;
- erro de parser.

---

# 29. Performance

O software deve lidar com:

- dezenas a centenas de milhares de moléculas em metadata;
- milhares a dezenas de milhares de poses;
- milhões de interaction observations.

Regras:

1. Não carregar todas as tabelas no GUI.
2. Paginação/virtual models.
3. Queries indexadas.
4. Processar imports em streaming/chunks.
5. Parquet para análises grandes.
6. Não serializar coordenadas grandes dentro do SQLite sem necessidade.
7. Manter paths e hashes.
8. Background workers para parsing.

Criar índices para:

```text
compound_id
molecular_state_id
target_id
run_id
pose_id
score_definition_id
import_batch_id
source alias
```

---

# 30. Segurança e robustez

- nunca executar arquivos importados;
- nunca executar GOLD/Vina/GROMACS como efeito colateral de import;
- tratar arquivos como dados;
- proteger contra path traversal em projetos portáveis;
- limite de tamanho de JSON/CSV preview;
- validação de ZIP;
- SQLAlchemy parametrizado;
- não usar pickle para projetos;
- não usar `eval()` em regras;
- decision expressions devem usar parser próprio.

---

# 31. Licenciamento

Antes do primeiro release:

1. escolher licença do FideliChem;
2. auditar dependências;
3. não copiar código GPL de SMILES2Docking se o FideliChem não adotar licença compatível;
4. não distribuir GOLD;
5. não distribuir assets proprietários;
6. citar ferramentas e algoritmos científicos.

Adapters devem interpretar saídas do usuário.

---

# 32. Configuração recomendada do Codex

A documentação atual do Codex permite custom agents em:

```text
.codex/agents/
```

com:

```text
model
model_reasoning_effort
sandbox_mode
developer_instructions
```

e limites globais em:

```text
.codex/config.toml
```

## 32.1 `.codex/config.toml`

```toml
[agents]
enabled = true
max_concurrent_threads_per_session = 6
default_subagent_model = "gpt-5.6-luna"
default_subagent_reasoning_effort = "xhigh"
```

Por que 6:
- suficiente para paralelizar exploração;
- reduz conflitos;
- evita spawn excessivo.

Não manter seis writers simultâneos.

---

# 33. Custom agents recomendados

## 33.1 `luna-explorer.toml`

```toml
name = "luna_explorer"
description = "Read-only repository explorer for mapping code, formats, schemas, fixtures, and execution paths."
model = "gpt-5.6-luna"
model_reasoning_effort = "xhigh"
sandbox_mode = "read-only"

developer_instructions = """
Work only on the bounded exploration task delegated by the parent.
Trace real files, symbols, schemas, formats, and tests.
Return concise evidence with paths and exact findings.
Do not edit files.
Do not propose broad redesigns unless explicitly asked.
If information is uncertain, state what fixture or test is needed.
"""
```

## 33.2 `luna-adapter.toml`

```toml
name = "luna_adapter"
description = "Implementation specialist for one FideliChem adapter at a time."
model = "gpt-5.6-luna"
model_reasoning_effort = "xhigh"
sandbox_mode = "workspace-write"

developer_instructions = """
Implement only the assigned adapter or parser.
Respect the EvidenceAdapter contract.
Do not write directly to the database from adapters.
Preserve raw values and provenance.
Add fixtures and tests for every supported branch.
Do not modify unrelated adapters or architecture.
Run targeted tests before returning.
"""
```

## 33.3 `luna-worker.toml`

```toml
name = "luna_worker"
description = "Cost-efficient implementation agent for narrow, well-specified core tasks."
model = "gpt-5.6-luna"
model_reasoning_effort = "xhigh"
sandbox_mode = "workspace-write"

developer_instructions = """
Implement the smallest complete change that satisfies the delegated task.
Follow existing architecture and type contracts.
Do not broaden scope.
Add or update tests.
Run relevant tests and report changed files, tests, and remaining risks.
"""
```

## 33.4 `luna-tests.toml`

```toml
name = "luna_tests"
description = "Test engineer for scientific regression, parser, integration, and edge-case coverage."
model = "gpt-5.6-luna"
model_reasoning_effort = "xhigh"
sandbox_mode = "workspace-write"

developer_instructions = """
Focus on tests, fixtures, edge cases, determinism, idempotency, and regression protection.
Prefer tests that would catch scientifically misleading behavior.
Do not change production logic unless the parent explicitly delegates a minimal testability change.
Return uncovered risks.
"""
```

## 33.5 `luna-docs.toml`

```toml
name = "luna_docs"
description = "Documentation and provenance specialist."
model = "gpt-5.6-luna"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"

developer_instructions = """
Update technical documentation only for behavior already implemented and verified.
Document file formats, adapter contracts, scientific caveats, and reproducibility semantics.
Never claim validation not demonstrated by tests.
"""
```

## 33.6 `terra-reviewer.toml`

```toml
name = "terra_reviewer"
description = "Integration reviewer for correctness, scientific semantics, architecture boundaries, and missing tests."
model = "gpt-5.6-terra"
model_reasoning_effort = "xhigh"
sandbox_mode = "read-only"

developer_instructions = """
Review as a scientific software maintainer.
Prioritize data integrity, provenance, identity resolution, score semantics,
scientific correctness, compatibility, migrations, and tests.
Do not make code changes.
Return findings ordered by severity with file references.
"""
```

## 33.7 `sol-architect.toml`

```toml
name = "sol_architect"
description = "Escalation-only architecture agent for difficult cross-cutting decisions."
model = "gpt-5.6-sol"
model_reasoning_effort = "xhigh"
sandbox_mode = "read-only"

developer_instructions = """
Use only for high-impact architectural or scientific decisions that remain unresolved
after normal Luna/Terra work.
Compare alternatives, migration cost, testability, scientific risk, and reversibility.
Prefer the simplest architecture that preserves future extensibility.
Do not edit files.
"""
```

---

# 34. Estratégia de spawn

## 34.1 Regra geral

Para cada fase:

### Passo A — exploração paralela

Spawn 2–4 agentes Luna read-only.

Exemplo:

```text
Spawn:
- luna_explorer: mapear arquivos e contratos existentes
- luna_explorer: mapear testes e riscos
- luna_explorer: pesquisar edge cases do formato
```

Aguardar todos.

### Passo B — síntese pelo agente principal

O parent:
- resolve conflitos;
- define contrato;
- registra decisão.

### Passo C — implementação

Spawn **1 writer por área independente**.

Não permitir:

```text
writer A -> storage/models.py
writer B -> storage/models.py
```

simultaneamente.

Pode permitir:

```text
writer A -> adapters/gold/*
writer B -> adapters/generic_table/*
```

se os contratos já estiverem congelados.

### Passo D — testes independentes

Spawn `luna_tests`.

### Passo E — revisão

Spawn `terra_reviewer`.

### Passo F — correção

Usar `luna_worker`.

### Passo G — gate

Somente avançar após suite verde.

---

# 35. Quando NÃO usar subagent

Não spawnar para:

- mudança de uma linha;
- rename trivial;
- formatter;
- comando simples;
- integração que depende intensamente de decisões tomadas segundos antes;
- edição de arquivo central onde outro agent já está trabalhando.

Subagents são úteis quando reduzem poluição de contexto ou paralelizam trabalho realmente independente.

---

# 36. Fases de implementação

---

## FASE 0 — Bootstrap e decisões arquiteturais

### Objetivo
Criar projeto vazio, padrões e contratos.

### Spawn

```text
1x luna_explorer
- revisar este plano e listar ambiguidades arquiteturais

1x luna_explorer
- propor dependency set mínimo e packaging

1x luna_tests
- desenhar estratégia de fixtures e test taxonomy
```

Aguardar.

### Parent
Consolidar.

### Implementação
`luna_worker`:
- pyproject;
- src layout;
- logging;
- CLI bootstrap;
- Qt bootstrap;
- pytest;
- CI;
- `.codex`;
- `AGENTS.md`.

### Gate
`terra_reviewer`.

### Aceite
- app inicia;
- CLI responde `--version`;
- pytest roda;
- CI roda;
- nenhum domínio científico ainda.

---

## FASE 1 — Domain model + storage

### Spawn

```text
luna_explorer A:
revisar modelo relacional e chaves

luna_explorer B:
procurar riscos de migrations/provenance

luna_tests:
propor invariantes de banco
```

### Implementar
- entidades;
- repositories;
- migrations;
- ImportBatch;
- SourceArtifact;
- audit log.

### Invariantes
- raw evidence imutável;
- import batch reversível;
- foreign keys ativas;
- ids internos estáveis;
- hashes preservados.

### Testes
- create/read;
- rollback;
- migration;
- cascade cuidadosamente definido;
- transaction failure.

### Gate
Terra.

---

## FASE 2 — Chemistry + Identity Resolver

### Spawn

```text
luna_explorer:
mapear normalização RDKit

luna_explorer:
mapear diferenças Compound vs MolecularState

luna_tests:
criar casos de stereo/protomer/tautomer
```

### Implementar
- canonicalization service;
- InChIKey service;
- structure hash;
- Compound;
- MolecularState;
- Alias;
- matching engine;
- ambiguity report.

### Casos obrigatórios
- mesmo SMILES em fontes diferentes;
- mesmo composto com IDs diferentes;
- estereoisômeros;
- cargas diferentes;
- tautômeros;
- missing SMILES;
- apenas alias;
- conflito alias/structure.

### Gate
Terra.

Não avançar se merges silenciosos ainda forem possíveis.

---

## FASE 3 — Adapter SDK + Import Manager

### Spawn

```text
luna_explorer:
desenhar adapter protocol

luna_explorer:
desenhar transaction flow

luna_tests:
adapter contract tests
```

### Implementar
- `EvidenceAdapter`;
- registry;
- detection;
- plan;
- parse;
- validate;
- persistence;
- rollback;
- duplicate import detection;
- entry points.

### Aceite
Criar FakeAdapter que passe pelo pipeline completo.

---

## FASE 4 — Universal Table Importer

Primeiro adapter real.

### Spawn

```text
luna_adapter:
CSV/TSV/Parquet

luna_adapter:
XLS/XLSX

luna_explorer:
JSON/JSONL mapping

luna_tests:
edge cases e presets
```

Os writers podem atuar em módulos independentes após contrato congelado.

### Implementar wizard GUI depois do core.

Primeiro:
- CLI + programmatic mapping.

### Aceite
Qualquer tabela simples de scores pode ser importada sem código novo.

---

## FASE 5 — Score Registry + normalization

### Spawn

```text
luna_explorer:
revisar directionality e comparability scopes

luna_tests:
casos higher_better/lower_better/ties/missing
```

### Implementar
- ScoreDefinition;
- registry;
- percentile;
- rank;
- robust z opcional;
- missing-aware calculations.

### Critério científico
Raw nunca muda.

### Gate
Terra.

---

## FASE 6 — GOLD Adapter

Esta é uma fase grande.

### Spawn inicial

```text
luna_explorer A:
mapear fixtures GOLD e nomes de arquivos

luna_explorer B:
mapear estrutura de ranking/solutions

luna_explorer C:
mapear scoring/rescoring semantics

luna_tests:
desenhar golden test matrix
```

### Congelar formato interno.

### Spawn de implementação

```text
luna_adapter A:
folder detection + plan

luna_adapter B:
ranking parser

luna_adapter C:
MOL2 solution parser

luna_tests:
fixtures + integration
```

Somente paralelizar se cada um editar arquivos independentes.

### Depois
Parent integra.

### Revisão
Terra.

### Aceite obrigatório

Importar:

```text
1 target
2 docking runs
>= 2 ligands
>= 3 poses/ligand
ChemPLP
GoldScore
ChemScore
ASP
```

quando presentes.

Manter scores separados.

Detectar inconsistências.

---

## FASE 7 — SMILES2Select + SMILES2Docking

Podem ser parcialmente paralelos.

### Spawn

```text
luna_adapter:
SMILES2Select SQLite/XLSX

luna_adapter:
SMILES2Docking JSON/structures

luna_tests:
cross-identity fixtures
```

### Integração crítica

Teste:

```text
SMILES2Select ID
        ↓
SMILES2Docking state
        ↓
GOLD ligand alias
```

deve resolver para Compound/MolecularState correto.

### Gate
Terra.

---

## FASE 8 — DockLens Adapter

### Spawn

```text
luna_explorer:
mapear saídas DockLens estáveis

luna_explorer:
mapear pose/source IDs e profiles

luna_tests:
interaction fixtures
```

### Implementar
- summary;
- detailed interactions;
- occupancy/frequency;
- fingerprints quando exportáveis;
- provenance;
- profile.

### Teste essencial

```text
GOLD Pose P003
      ↓
DockLens interactions
```

deve associar à mesma pose.

### Gate
Terra.

---

## FASE 9 — MolDynStudio + GROMACS analytics

### Spawn

```text
luna_explorer:
mapear saídas MolDynStudio

luna_adapter:
XVG parser

luna_tests:
multi-series XVG

luna_explorer:
definir metric registry MD
```

### Implementar
- MDRun;
- metric registry;
- MolDynStudio adapter;
- GROMACS analytical outputs.

### Não implementar
XTC/TRR trajectory engine.

### Gate
Terra.

---

## FASE 10 — Analytics Engine

### Spawn

```text
luna_worker:
score consensus

luna_worker:
agreement metrics

luna_worker:
Pareto

luna_tests:
scientific regression suite
```

Pode paralelizar porque módulos distintos.

### Depois
Parent integra.

### Terra reviewer
Revisar:
- missing values;
- ties;
- score direction;
- comparability scopes;
- reproducibility.

---

## FASE 11 — Pose Consensus

### Spawn

```text
luna_explorer:
RDKit atom mapping options

luna_worker:
RMSD matrix

luna_worker:
clustering/medoid

luna_tests:
symmetry and atom-order cases
```

### Atenção
Átomos equivalentes/simetria podem causar RMSD enganoso.

Escalar para Terra se necessário.

Sol somente se continuar cientificamente ambíguo após revisão.

---

## FASE 12 — Interaction Consensus

### Implementar
- interaction key;
- prevalence;
- residue/type matrix;
- pose family comparison.

### Testar
- zero-contact poses;
- denominadores;
- múltiplos profiles;
- duplicatas atom-pair.

---

## FASE 13 — Decision Engine

### Spawn

```text
luna_explorer:
propor schema de profiles

luna_worker:
parser/validator

luna_worker:
explanation engine

luna_tests:
deterministic regression
```

### Gate Terra obrigatório.

### Requisito
Toda prioridade deve produzir explicação.

Nunca apenas:

```text
score = 0.81
```

---

## FASE 14 — GUI completa

Dividir por áreas.

### Spawn

```text
luna_worker:
project/import screens

luna_worker:
compound explorer

luna_worker:
decision/QC views

luna_tests:
pytest-qt flows
```

Antes, congelar services/interfaces.

Não colocar queries SQL diretamente nos widgets.

---

## FASE 15 — Export + reproducibility

### Implementar
- CSV;
- XLSX;
- Parquet;
- JSON manifest;
- methods report;
- charts.

### Spawn
Luna.

### Gate
Terra.

---

## FASE 16 — Packaging e release

### Windows
- installer ou portable.

### Ubuntu
- `.deb`, AppImage ou portable tar.

Escolher dois formatos sustentáveis, não quatro por plataforma no início.

### CI
- tests;
- packaging smoke test;
- SHA256SUMS;
- release artifact.

### Final review

Spawn:

```text
terra_reviewer:
arquitetura e regressões

terra_reviewer:
scientific semantics

luna_tests:
full regression
```

Sol somente se houver bloqueador crítico.

---

# 37. Workflow recomendado por issue

Cada issue deve usar:

```text
Problem
Scope
Non-goals
Files likely affected
Scientific invariants
Acceptance criteria
Tests required
Migration impact
```

Exemplo:

```text
Issue: GOLD ChemPLP import

Scope:
- parse ChemPLP from supported GOLD fixture
- attach score to pose
- preserve raw score
- define direction higher_better

Non-goals:
- rescoring
- GUI

Acceptance:
- fixture imports 20 poses
- all pose IDs stable
- score values exact
- second import detected as duplicate
```

---

# 38. Prompt mestre sugerido para iniciar o Codex

Use o conteúdo abaixo no primeiro turno do Codex após criar o repositório:

```text
Você é o agente principal de implementação do FideliChem.

Leia integralmente FIDELICHEM_PLAN_CODEX.md e AGENTS.md antes de editar qualquer arquivo.

Implemente o projeto estritamente por fases. Não antecipe machine learning, FEP ou execução automática de docking/MD.

Use subagents ativamente.

Política de custo:
- use gpt-5.6-luna com reasoning xhigh para a maioria das tarefas;
- use Terra xhigh para revisão de integração e problemas transversais;
- use Sol apenas como escalonamento excepcional.

No início de cada fase:
1. identifique tarefas independentes;
2. spawn subagents Luna para exploração/testes;
3. espere os resultados;
4. consolide o contrato;
5. só então delegue implementação;
6. evite writers simultâneos nos mesmos arquivos;
7. rode testes;
8. peça revisão Terra no gate da fase.

Não altere decisões científicas silenciosamente.
Preserve sempre dados brutos, provenance e auditabilidade.

Comece somente pela FASE 0.
Ao concluir a fase, reporte:
- arquivos criados/alterados;
- testes executados;
- decisões tomadas;
- riscos;
- critérios de aceite atendidos;
- qual é a próxima fase.

Não avance automaticamente para a próxima fase sem fechar o gate atual.
```

---

# 39. Modelo de prompt de spawn para Luna

```text
Spawn luna_explorer for the following bounded task.

Task:
Map the current GOLD adapter requirements for Phase 6.

Read-only.

Return:
1. files/formats that must be supported;
2. exact data fields expected;
3. ambiguities;
4. edge cases;
5. recommended fixtures;
6. risks to identity/provenance.

Do not implement anything.
Do not redesign unrelated modules.
Wait for completion and return a concise evidence-based summary.
```

---

# 40. Modelo de prompt de implementação Luna

```text
Spawn luna_adapter.

Implement only:
GOLD bestranking parser.

Constraints:
- follow EvidenceAdapter contracts already defined;
- do not write to the database;
- preserve raw values;
- return canonical objects;
- do not change score normalization;
- do not touch GUI;
- add focused fixtures and tests.

Run targeted tests.

Return:
- changed files;
- implemented behavior;
- tests;
- unresolved format ambiguities.
```

---

# 41. Modelo de prompt de revisão Terra

```text
Spawn terra_reviewer in read-only mode.

Review Phase 6 GOLD adapter.

Focus on:
- scientific score semantics;
- pose-to-score mapping;
- run separation;
- provenance;
- identity resolution;
- duplicate imports;
- error handling;
- tests;
- backward migration risk.

Do not edit.

Return findings ordered:
CRITICAL
HIGH
MEDIUM
LOW

Include file paths and concrete remediation.
```

---

# 42. Critério para escalar ao Sol

O parent só deve chamar `sol_architect` quando pelo menos uma condição ocorrer:

1. dois Luna chegam a conclusões incompatíveis e Terra não resolve;
2. decisão pode exigir migration destrutiva;
3. decisão afeta todos os adapters;
4. identidade química tem risco científico relevante;
5. score normalization pode produzir ranking enganoso;
6. bug permanece após duas tentativas independentes;
7. arquitetura atual impediria extensão multi-fidelity futura.

Não usar Sol para:
- boilerplate;
- parser simples;
- teste;
- documentação;
- GUI local;
- refactor pequeno.

---

# 43. Marcos de release

## v0.1.0 — Evidence Core

- project;
- DB;
- provenance;
- identity;
- generic tables;
- score registry.

## v0.2.0 — Docking Evidence

- GOLD;
- SMILES2Select;
- SMILES2Docking;
- score normalization;
- consensus básico.

## v0.3.0 — Interaction Evidence

- DockLens;
- pose consensus;
- interaction consensus.

## v0.4.0 — Dynamic Evidence

- MolDynStudio;
- GROMACS analytic outputs;
- MD registry.

## v0.5.0 — Decision

- Pareto;
- decision profiles;
- explanations;
- QC completo.

## v1.0.0

- GUI madura;
- export;
- packaging;
- migration;
- reproducibility;
- documentation;
- regression suite.

## v1.x

- Vina;
- GNINA;
- Glide;
- PLANTS;
- outros adapters.

## v2.0

- active learning;
- uncertainty;
- cost-aware multi-fidelity;
- Next Best Evidence inteligente.

## v3.0

- FEP/experimental closed loop, se necessário.

---

# 44. Métricas de sucesso do MVP

O software está pronto para 1.0 quando consegue:

1. importar uma campanha com SMILES2Select;
2. associar estruturas/estados do SMILES2Docking;
3. importar dois ou mais runs GOLD;
4. preservar ChemPLP/GoldScore/ChemScore/ASP separadamente;
5. associar poses GOLD a interações DockLens;
6. importar pelo menos um conjunto de métricas MD;
7. reconciliar IDs diferentes da mesma molécula;
8. detectar conflitos de estado molecular;
9. gerar consenso de scores sem misturar escalas brutas;
10. gerar Pareto;
11. explicar prioridade de cada candidato;
12. desfazer um import batch;
13. abrir o projeto novamente sem perda;
14. exportar resultados reprodutíveis;
15. passar a suite completa em Windows e Linux.

---

# 45. Princípios científicos que não podem ser quebrados

1. **Raw data is immutable.**
2. **Scores de métodos diferentes não são diretamente equivalentes.**
3. **Molécula ≠ estado molecular.**
4. **Pose ≠ composto.**
5. **Docking score ≠ binding affinity experimental.**
6. **MD stability metric ≠ eficácia.**
7. **Ausência de dado ≠ resultado negativo.**
8. **Missing values não podem virar zero silenciosamente.**
9. **Run boundaries devem ser preservados.**
10. **Denominadores devem ser explícitos.**
11. **Toda transformação deve ser rastreável.**
12. **Toda decisão deve ser explicável.**
13. **Todo merge de identidade ambígua deve ser confirmável e reversível.**
14. **Todo método deve declarar unidade e directionality.**
15. **Nenhuma IA futura poderá alterar dados brutos.**

---

# 46. Dívida técnica proibida

Não aceitar no PR:

```text
- adapter escrevendo SQL diretamente
- if engine == "gold" espalhado no core
- GUI contendo regra científica
- dataframe global como estado do projeto
- pickle como formato persistente
- score genérico sem ScoreDefinition
- coluna "score" sem provenance
- merge por filename apenas
- uso de média de raw scores heterogêneos
- thresholds científicos hardcoded em widget
- strings de interação sem registry
- deletar import sem transaction
- parser sem fixture
- migration sem teste
```

---

# 47. Decisões que devem ser registradas como ADR

Criar:

```text
docs/decisions/
```

ADR obrigatórios:

```text
0001-project-storage.md
0002-compound-vs-state.md
0003-adapter-contract.md
0004-score-normalization.md
0005-identity-resolution.md
0006-import-rollback.md
0007-gold-run-model.md
0008-docklens-interaction-model.md
0009-md-metric-model.md
0010-decision-engine.md
```

---

# 48. Documentação mínima para cada adapter

```text
Adapter
Supported versions
Supported files
Auto-detection
Required files
Optional files
Imported evidence
Identity strategy
Score direction
Units
QC checks
Known limitations
Example command
Fixture coverage
```

---

# 49. Referências de configuração do Codex

Estas referências devem ser verificadas novamente pelo agente de implementação se o Codex for atualizado:

- Codex subagents:
  https://developers.openai.com/codex/subagents/

- GPT-5.6 model guidance:
  https://developers.openai.com/api/docs/guides/latest-model

- Codex pricing:
  https://help.openai.com/pt-br/articles/20001106

Na documentação atual, custom agents podem definir `model`, `model_reasoning_effort` e `sandbox_mode`, e configurações globais permitem escolher modelo/effort padrão dos subagents e limitar threads concorrentes.

---

# 50. Resultado final desejado

Ao final do desenvolvimento, o FideliChem deve permitir que um pesquisador faça:

```text
Novo projeto
    ↓
Importar SMILES2Select
    ↓
Importar GOLD run 1
    ↓
Importar GOLD run 2
    ↓
Importar DockLens
    ↓
Importar MolDynStudio/GROMACS
    ↓
Reconciliar identidades
    ↓
Auditar QC
    ↓
Comparar scoring functions
    ↓
Comparar poses
    ↓
Comparar interações
    ↓
Adicionar evidência dinâmica
    ↓
Aplicar política de decisão
    ↓
Identificar candidatos prioritários
    ↓
Saber exatamente POR QUE cada candidato avançou
```

O software não deve responder apenas:

> "MOL001 ficou em primeiro."

Ele deve responder:

> "MOL001 foi priorizada porque está no percentil 96 de ChemPLP, percentil 93 de GoldScore, apresenta alta concordância entre funções de pontuação, mantém as interações-chave definidas para o alvo e possui evidência dinâmica favorável. Os valores brutos, arquivos de origem e transformações permanecem disponíveis para auditoria."

Esse é o critério final de qualidade do FideliChem:

> **integração agnóstica de origem + rastreabilidade + evidência molecular + decisão científica explicável.**
