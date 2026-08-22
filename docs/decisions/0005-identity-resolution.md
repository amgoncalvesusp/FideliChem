# ADR 0005: Auditable identity resolution and reversible evidence

- Status: Accepted
- Date: 2026-08-22

## Context

Source aliases are evidence, not durable chemical identity. Resolution must
be deterministic and read-only until an explicit, report-authorized human or
system confirmation. The catalog must remain useful after an alias is
retracted or an import batch is rolled back, while active alias projections
must not expose inactive evidence.

## Decision

The pure resolver emits one of the following outcomes:

- `NEW_COMPOUND`: no structural catalog match; `confirm_claim` may create the
  compound and exact state atomically;
- `NEW_STATE`: a single parent compound matches but the exact state is new;
  confirmation reuses that compound and creates the exact state;
- `EXACT_STATE`: the exact state is present and can be reused;
- `ALIAS_ONLY`, `AMBIGUOUS`, `CONFLICT`, or `UNRESOLVED`: evidence is retained
  in the report but does not authorize automatic catalog creation or merge.

The persistent index has two deliberately different read-only projections:

1. immutable catalog queries search all validated compound/state rows,
   including rows whose aliases are dormant; and
2. `active_by_alias` follows the current append-only resolution leaf and
   filters superseded, retracted, and rolled-back evidence.

Dormancy is candidate-granular. A dormant exact-state or parent candidate is
  marked dormant without hiding an independent active candidate for the same
  compound or a sibling state. Structural catalog reuse therefore remains
  available after retraction and rollback, while inactive alias evidence is
  absent from the active projection.

`IdentityClaim` values without a complete source pair and non-null
`import_batch_id` remain valid for in-memory resolution only. They can never
be persisted. The exact persistence boundary is the frozen signature:

```python
confirm_claim(
    result: CanonicalizationResult | None,
    claim: IdentityClaim,
    report: ResolutionReport,
    selection: IdentitySelection,
    actor: IdentityActor,
) -> IdentityResolution
```

`confirm_claim` rejects missing persistence prerequisites before opening a
unit-of-work. It accepts only a selection listed by the immutable report (or
the explicit `NEW_COMPOUND` selection), revalidates the report against the
live index, and rejects stale or unauthorized targets without writing. A
`CONFLICT` report never authorizes an automatic merge, but a user may make an
explicit, rationale-bearing choice among report-listed targets. A system actor
may confirm only unambiguous structural
`EXACT_STATE`, `NEW_STATE`, or `NEW_COMPOUND` outcomes. Alias-only,
ambiguous, conflicting, and human mutation decisions require a user actor and
nonblank rationale. InChI warnings and identity evidence are written into the
same batch-correlated audit event as the confirmation; there is no separate
half-committed warning event.

The service receives its clock only in the constructor. Human `reassign`,
`retract`, and `restore` operations are report-free: they validate existing
compound/state targets and state ownership directly, then append one audited
resolution in one transaction. A state target must belong to the selected
compound. Alias uniqueness is enforced per
`(import_batch_id, source_system, source_value)`. Database constraints and
repository checks protect root/successor uniqueness, alias ownership, state
ownership, append-only rows, and concurrent races.

Resolution chains are explicit. A `RETRACTED` node follows only a targeted
`CONFIRMED`, `REASSIGNED`, or `RESTORED` node. Repeated retraction is rejected.
Only a user with a nonblank rationale may create `RESTORED`, and it must name
an explicit existing target and a `RETRACTED` predecessor. The restored node
can itself be retracted, preserving the complete raw lineage for audit.

## Consequences

Catalog reuse is stable across project close/reopen and import rollback, but
source aliases remain reversible and auditable. Structural conflicts cannot be
silently confirmed. Selection and actor values are typed at the service
boundary, and all mutations are atomic with their audit event. Concurrent
writers have one authoritative winner per alias/root/successor constraint and
revalidate live state before committing.

This ADR does not add adapter parsing, GUI authority, target/pose semantics,
or automatic resolution of ambiguous evidence. Future adapters must preserve
raw evidence and call this service rather than writing identity tables.

## Evidence

`tests/integration/identity/test_phase2_workflow.py` exercises the real project
create/reopen path, report-bound selections, resolver-only claims, conflict
no-mutation, InChI-warning audit, alias-only confirmation, reassign/retract/
restore chains, dormant catalog reuse, and Phase 1 rollback. Existing identity
service, projection, audit, repository, and concurrency tests provide the
focused evidence for the matrix and race guarantees described here.
