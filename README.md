# Accounting Agentic System

A **local-first, hybrid multi-agent accounting workflow** for importing bank transactions, categorizing expenses, flagging exceptions, and posting records **only after human approval**.

Built with **Python, SQLite, optional Claude CLI reasoning, and pluggable Plaid/Akaunting adapters**. The focus is on reliable workflow orchestration, safe tool use, and clear audit trails—not an autonomous finance chatbot.

> **Scope:** This is a working local proof of concept using fictional data. It does not move money, file taxes, or replace a production accounting system.

## What it does

- **Ingest:** Read a local CSV or sync Plaid Sandbox transactions; normalize records and avoid duplicate imports.
- **Categorize:** Use transparent merchant rules, with optional `claude -p` suggestions for ambiguous expenses.
- **Check policies:** Hold pending transactions, transfers, income, high-value expenses, and low-confidence classifications.
- **Reconcile exceptions:** Flag changed/removed bank transactions and uncertain external posting outcomes for manual review.
- **Approve and post:** Require an identified human reviewer before writing to the local ledger or an explicitly selected accounting sink.
- **Audit:** Record decisions and state changes in SQLite; expose a token-protected, read-only reporting API.

## Architecture

```text
CSV / Plaid Sandbox
       |
       v
Ingestion & deduplication
       |
       v
Categorization (rules + optional Claude reasoning)
       |
       v
Policy checks & reconciliation flags
       |
       v
Human review / approval
       |
       +---- Hold / investigate
       |
       +---- Approved --> SQLite ledger / optional Akaunting adapter
                                  |
                                  v
                              Audit trail
```

These are **specialized workflow components coordinated by Python**, not independent autonomous LLMs. Claude can suggest a category; it cannot approve or execute financial actions.

For the component diagram, design decisions, security boundaries, and literature review, see [docs/workflow.md](docs/workflow.md).

## Quick start

**Requirements:** Python 3.10+; the local demo uses Python's standard library. Run commands from the repository root.

```powershell
# Optional: install declared dependencies
python -m pip install -r requirements.txt

# Import 8 fictional transactions and generate review proposals
python src/app.py demo

# Inspect proposals (copy the ID of an item with status "review")
python src/app.py review
```

**Approve and post an expense:**

```powershell
python src/app.py approve --id YOUR_ID --reviewer accountant
python src/app.py post --id YOUR_ID
python src/app.py report
python src/app.py audit
```

Replace `YOUR_ID` with a real proposal ID from `review`. No expense is posted automatically. Re-running `demo` against the same database reports duplicates rather than importing them twice.

### Import a CSV

```powershell
python src/app.py sync --file src/data/sample_bank.csv --account-alias demo
python src/app.py process
python src/app.py review
```

The CSV under `src/data/` is fictional. Generated SQLite files and evaluation outputs belong under `artifacts/` and should stay out of Git.

## Optional integrations

| System | Role | Status |
| --- | --- | --- |
| CSV + SQLite | Local ingestion, ledger state, audit log | Implemented and tested locally |
| Claude CLI | Optional category reasoning for uncertain expenses | Implemented; live CLI call requires your environment |
| Plaid Sandbox | Incremental bank transaction synchronization | Adapter implemented; behavior tested with mocks, not live credentials |
| Akaunting | Export approved expenses | Adapter implemented; live instance not verified |
| Custom adapters | Add another bank or accounting system | Python extension interface available |

**Claude:** With a working Claude CLI and the assignment-provided `CLAUDE_KEY` environment variable, opt in using:

```powershell
python src/app.py --db artifacts/claude-demo.sqlite demo --reasoner claude
```

The application calls `claude -p` with tools disabled. If reasoning is unavailable or invalid, the expense remains subject to manual review. No Anthropic API SDK is used.

**Plaid Sandbox:** Configure `PLAID_CLIENT_ID`, `PLAID_SECRET`, and `PLAID_ACCESS_TOKEN` in your local environment, then run:

```powershell
python src/app.py sync --source plaid
python src/app.py process
```

**Akaunting:** Set `AKAUNTING_BASE_URL`, `AKAUNTING_EMAIL`, `AKAUNTING_PASSWORD`, `AKAUNTING_ACCOUNT_ID`, `AKAUNTING_COMPANY_ID`, and `AKAUNTING_CATEGORY_IDS_JSON` in your local environment. After approving an expense, you can opt in to external posting:

```powershell
python src/app.py post --id YOUR_ID --sink akaunting --confirm-external
```

Custom connectors implement `sync(ledger)` or `post(approved_transaction)` and can be loaded through the `--plugin` option. Only use trusted local modules. **Do not commit credentials or real financial records.**

## Evaluation

```powershell
python -m unittest discover -s src/tests -t src -v
python src/eval.py
```

The evaluator writes `artifacts/eval.json`. In the current authored 11-case check, the keyword categorizer correctly labels all 11 examples; duplicate detection and the no-unapproved-posting check also pass. **This is a small, authored test set—not an estimate of accuracy on real bank data.**

Tests also cover approval restrictions, idempotency, modified/removed transactions, Plaid-style pagination, and uncertain external writes. The reported categorizer latency measures rule lookup only, not a complete agent workflow or Claude calls.

The submission's entry-point commands are listed in root-level [`run.yaml`](run.yaml).

## Run the read-only API

```powershell
$env:APP_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
python src/app.py serve
```

The service listens on `127.0.0.1:8765`. Available endpoints: `GET /health`, `GET /transactions`, `GET /proposals`, and `GET /report`. Except for `/health`, supply the header `Authorization: Bearer YOUR_TOKEN`. Write operations remain CLI-only.

A `Dockerfile` and Compose configuration are included as optional deployment scaffolding; container deployment must be validated separately, especially after source-directory moves.

## Project structure

```text
src/
  app.py, core.py, adapters.py, hooks.py, server.py, eval.py
  data/sample_bank.csv
  tests/
docs/
  workflow.md
README.md
requirements.txt
run.yaml
Dockerfile                # optional deployment
docker-compose.yml        # optional deployment
.gitignore
artifacts/                # generated locally; not committed
```

## Design rationale and research

This design follows the reasoning-and-action approach of [ReAct](https://arxiv.org/abs/2210.03629) and the role specialization discussed in [AutoGen](https://arxiv.org/abs/2308.08155). [τ-bench](https://arxiv.org/abs/2406.12045) motivates measuring final-state correctness and policy compliance; [AgentDojo](https://arxiv.org/abs/2406.13352) motivates strict boundaries around untrusted tool inputs.

Accounting-specific benchmarks—[APEX-Accounting](https://arxiv.org/abs/2607.27189), [FinRCA-Bench](https://arxiv.org/abs/2608.18534), [FinBalance](https://arxiv.org/abs/2606.15949), and [Finch](https://aclanthology.org/2026.findings-acl.523/)—inform future evaluation of reconciliation, accounting correctness, and multi-step workflows. **Those benchmarks have not been run on this implementation.**

## Current limitations

- Local-first proof of concept, not a general ledger or full bank-to-ledger reconciliation engine.
- USD-only sample workflow; no payments, transfers, tax filing, or automated journal balancing.
- No live Plaid/Akaunting integration testing or production bank authorization flow.
- Production use would require stronger identity/access controls, encryption, webhook verification, backups, and operational monitoring.

**Design principle:** *Use AI to recommend, deterministic code to enforce policy, and a human to authorize financial changes.*
