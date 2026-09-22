# Ragged Claws — Runtime and Deployment Strategy

**Status:** Draft v0.1  
**As of:** 2026-09-22  
**Scope:** Bootstrap runtime, durable state, and infrastructure upgrade gates

## 1. Objective

Ragged Claws should remain operationally lean until the research system demonstrates enough value to justify recurring infrastructure expense.

The bootstrap target is not a traditional always-on application server. The preferred initial operating model is:

```text
GitHub
  ├── source code
  ├── issues / PRs
  └── CI + scheduled workflows
        ↓
GitHub Actions ephemeral runner
        ↓
local temporary DataLayout
        ↓
Cloudflare R2 durable object storage
```

This preserves the existing local-first storage architecture while avoiding a permanent server until one is measurably useful.

## 2. Responsibilities by platform

### GitHub

GitHub is the code/control plane.

Use it for:

- repository source;
- documentation;
- issues and pull requests;
- CI;
- scheduled workflow definitions;
- deployment/runtime secrets needed by Actions.

Git is not the research-data warehouse. Bulk data, raw captures, database/cache files, credentials, and restricted vendor payloads remain outside the repository.

### GitHub Actions

GitHub-hosted runners are the preferred bootstrap unattended compute layer where workflow duration and resource limits remain practical.

Expected jobs include:

- periodic source ingestion;
- normalization/canonicalization;
- validation;
- DuckDB catalog rebuild;
- research-output regeneration;
- scheduled integrity checks.

Runners are ephemeral. No workflow may assume runner-local state survives after the job ends.

### Cloudflare R2

R2 is the preferred first durable object-storage service for unattended operation.

It should hold durable research state between ephemeral runs, subject to source retention/license rules:

```text
raw/
staging/
curated/
research/
snapshots/
```

Do not persist disposable state merely because storage is available.

Normally exclude:

```text
cache/
cache/catalog.duckdb
```

DuckDB is rebuildable from authoritative Parquet and should remain disposable.

R2 is chosen for bootstrap economics and operational fit, not because canonical code should depend on Cloudflare-specific semantics. Prefer the S3-compatible boundary where practical.

### Windows development machine

The local Windows environment remains useful for:

- development;
- local test runs;
- fixture inspection;
- ad hoc research;
- manual validation;
- optional local mirrors/backups of durable object state.

The personal workstation should not be required to remain powered on for scheduled production ingestion.

## 3. Existing storage model remains authoritative

The runtime plan does not change the storage contract established in M0.

```text
data/
├── raw/
├── staging/
├── curated/
├── research/
├── snapshots/
└── cache/
```

Semantics remain:

- raw captures are immutable/append-only;
- staging is source-normalized Parquet;
- curated Parquet is authoritative canonical analytical state;
- research outputs are reproducible derivatives;
- snapshots are intentionally frozen/versioned state;
- cache is disposable;
- DuckDB is rebuildable query/catalog state.

The cloud bootstrap should therefore add synchronization around the local filesystem model rather than making every adapter/storage class cloud-aware.

## 4. Intended unattended workflow

Conceptually:

```text
1. Check out main
2. Install locked Python environment
3. Acquire single-writer workflow lease/concurrency slot
4. Sync durable R2 state into temporary ./data/
5. Run ingestion / canonicalization
6. Run validation and integrity checks
7. Rebuild DuckDB locally where needed
8. Produce research outputs
9. Sync changed durable state back to R2
10. End runner; discard cache and local DuckDB
```

The synchronization implementation should preserve immutable raw objects and must not turn object storage into a last-write-wins escape hatch around canonical conflict rules.

## 5. Single-writer rule

M0 persistence is intentionally not a concurrent multi-writer system.

Scheduled production workflows must therefore serialize writes to the same durable state.

GitHub Actions should use an explicit concurrency group or equivalent guard so two scheduled/manual production runs cannot update the same R2-backed state at the same time.

Do not add distributed locking, queues, or orchestration systems until overlapping writers become a demonstrated requirement.

## 6. Secrets and credentials

Bootstrap secrets should be kept outside Git and exposed to unattended workflows through GitHub Actions secrets or another appropriately scoped secret mechanism.

Examples:

- R2 access credentials;
- future source API credentials;
- optional live-smoke-test credentials.

Use least-privilege credentials where practical. A runtime token that can read/write the Ragged Claws R2 bucket does not need broad Cloudflare account permissions.

Never place secrets in:

- committed `.env` files;
- workflow logs;
- raw manifests;
- test fixtures;
- research outputs.

## 7. Retention and licensing boundary

A technically convenient cloud bucket does not override source license or retention constraints.

Before synchronizing a source's raw payload to R2, confirm its retention class permits that storage posture.

Public primary-source records such as SEC filings are natural candidates for durable R2 storage.

Restricted/commercial provider responses must follow their applicable terms. Where raw cloud retention is not allowed or is unclear, preserve only the permitted derived/canonical state and keep the restricted payload in an approved location.

## 8. Bootstrap cost rule

Infrastructure target:

> **Approximately $0/month until a measurable free/freemium limitation appears.**

This does not mean avoiding useful spend at all costs. It means infrastructure purchases require a concrete reason.

Cloudflare is the preferred first paid infrastructure vendor when modest spending becomes necessary and its services fit the requirement cleanly.

Examples of acceptable future spend:

- R2 storage after free-tier capacity is exceeded;
- low-cost Cloudflare services that materially simplify a demonstrated workflow problem;
- a small persistent Linux node when ephemeral compute becomes inefficient.

## 9. Persistent-server upgrade gates

Do not provision a permanent VM merely because production systems traditionally have one.

Move to a persistent node when one or more of these becomes true:

1. GitHub Actions runtime/resource limits materially constrain ingestion or analysis.
2. Repeated R2 state transfer becomes slower or more expensive than persistent compute.
3. Long-running processes are genuinely required.
4. Stable local caches materially reduce cost/runtime.
5. Scheduling/recovery behavior becomes awkward on ephemeral runners.
6. A persistent service/API becomes necessary.
7. The strategy's demonstrated value makes modest reliability spend economically immaterial.

At that point the preferred migration remains boring:

```text
GitHub → deploy to small Linux node
R2     → durable storage / backup boundary
Parquet → remains authoritative
DuckDB  → remains rebuildable local query state
```

Avoid introducing Postgres, Redis, Kubernetes, Airflow, or other infrastructure merely as part of the VM migration unless a separate workload requires them.

## 10. Failure and recovery posture

The durable system should be recoverable from:

- GitHub repository state;
- R2 raw/curated/snapshot objects;
- documented configuration and schema versions.

A lost runner or deleted DuckDB file should not be a disaster.

The architecture should make the following recovery routine possible:

```text
clean runner or machine
→ checkout repository
→ restore durable object state
→ uv sync --frozen
→ validate Parquet
→ rebuild DuckDB
→ resume ingestion
```

## 11. Implementation timing

Do not block fixture-first M1 source-adapter development on cloud deployment work.

The R2 synchronization/scheduled-runtime layer should be implemented before Ragged Claws begins accumulating meaningful unattended live-source history.

Recommended sequence:

```text
M0 complete
    ↓
M1 SEC Form 4 fixture-first adapter
    ↓
prove real source semantics locally/CI
    ↓
add R2 durable-state sync + scheduled Actions production workflow
    ↓
start unattended live-source accumulation
```

This keeps infrastructure work subordinate to the evidence pipeline rather than becoming a parallel cloud-engineering project.

## 12. Architecture test for infrastructure purchases

Before adding a recurring infrastructure service, answer:

1. What measured constraint does it solve?
2. What is the recurring cost?
3. What operational risk does it reduce?
4. Can the existing free stack solve the problem acceptably?
5. Does it create vendor lock-in in canonical code or only at an replaceable boundary?
6. Can the system be reconstructed if the service disappears?
7. Is the expense justified relative to deployed capital and expected research value?

If those answers are weak, do not add the service.