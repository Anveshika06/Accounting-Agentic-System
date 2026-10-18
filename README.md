# Local Accounting Agent

A small multi-agent workflow that imports bank transactions, recommends expense categories, flags exceptions, and **only posts expenses after explicit human approval**. No payments or transfers are initiated. Built for a workflow/system-design exercise; it is **not a production-ready accounting system**.

## Try it (Python 3.10+, no packages needed)

From the repository root:

```bash
python src/app.py demo
python src/app.py review
python -m unittest discover -s tests -v
python src/eval.py
```

The demo imports 8 **fictional transactions** into `artifacts/ledger.sqlite` and creates review/hold proposals. Re-running it does not duplicate the transactions.

### Approve and post one local expense

1. Run `python src/app.py review` and copy the `id` of a `review` item.
2. Approve it with `python src/app.py approve --id THE_ID --reviewer accountant`.
3. Record it locally: `python src/app.py post --id THE_ID`.
4. See totals: `python src/app.py report`.

Approval is required even for obvious classifications. `held` means pending, high-value, transfer, income, or uncertain; a person may override the category for a reviewed settled expense, but cannot post a transfer or pending item.

## Connectors

**CSV (always works):**

```bash
python src/app.py sync --file data/sample_bank.csv --account-alias demo
python src/app.py process
```

**Plaid Sandbox (requires your own Sandbox credentials and an existing access token):** set `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ACCESS_TOKEN`, then:

```bash
python src/app.py sync --source plaid
python src/app.py process --reasoner rules
```

The sandbox connector uses `/transactions/sync` with pagination/cursors, detects bank updates, and blocks removed transactions. It **does not connect to a live account without separate Link setup and consent**. See `docs/workflow.md`.

**Claude reasoning, optional:** configure Claude Code CLI and `CLAUDE_KEY` as specified by your environment, then:

```bash
python src/app.py --db artifacts/claude-demo.sqlite demo --reasoner claude
```

Only uncertain, settled expenses are sent as minimized merchant/amount fields. The code calls `claude -p` (no Anthropic API client, no mapping `CLAUDE_KEY` into `ANTHROPIC_API_KEY`). If Claude is unavailable, the transaction remains for human review. `--tools ""` and strict MCP configuration prevent the model from taking actions.

**Akaunting:** An approved local expense can be explicitly exported using `python src/app.py post --id THE_ID --sink akaunting --confirm-external`. Configure `AKAUNTING_BASE_URL`, `AKAUNTING_EMAIL`, `AKAUNTING_PASSWORD`, `AKAUNTING_ACCOUNT_ID`, `AKAUNTING_COMPANY_ID`, and `AKAUNTING_CATEGORY_IDS_JSON` (a JSON object from category names to existing Akaunting IDs). **Test against your own Akaunting installation first**; no live Akaunting instance was available for verification. A failed/uncertain API write is never automatically retried.

**Other systems:** `python src/app.py sync --plugin my_company.bank:BankAdapter` or `python src/app.py post --id THE_ID --sink akaunting --plugin my_company.erp:LedgerSink --confirm-external`. Plug-ins are trusted local Python modules implementing `sync(ledger)` or `name` + `post(approved_tx)`. Only install/review trusted modules.

## Serve a read-only API

```bash
# Linux/macOS: export APP_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
# PowerShell: $env:APP_TOKEN = python -c "import secrets;print(secrets.token_urlsafe(32))"
python src/app.py serve
```

Routes: `GET /health`, `GET /transactions`, `GET /proposals`, and `GET /report`. Supply `Authorization: Bearer YOUR_TOKEN` except for health. All writes are CLI-only. `docker compose up --build` runs the same read-only API, mapped only to host loopback; set a strong `APP_TOKEN` in an uncommitted `.env` first. For remote use, add a trusted HTTPS reverse proxy, stronger identity/RBAC and proper secret management.

## What to submit

- `src/` working agents and connectors
- `docs/workflow.md` short workflow/system-design write-up with component diagram
- `docs/evaluation.md` measurable acceptance tests, guardrails and limits
- `run.yaml` **exact setup/test/demo commands**

`artifacts/` contains local financial-like data and must not be committed. All sample transactions are fictional. See `docs/evaluation.md` for what has and has not been tested.
