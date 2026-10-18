# Evaluation and guardrails

The goal is **correct workflow behavior**, not only a model answer. Run `python -m unittest discover -s tests -v` and `python src/eval.py`. Results are written to `artifacts/eval.json` (ignored by Git).

| Dimension | Metric / acceptance criterion | Evidence currently available |
|---|---|---|
| Ingestion correctness | 100% correctly parsed USD examples; 0 invalid rows accepted | Unit tests for money validation |
| Replays / idempotency | 0 duplicate rows or duplicate postings on rerun | Unit tests for two imports, double-post rejection |
| Categorization | Accuracy on a manually labeled merchant sample; aim ≥90% with review | **11 authored examples only**; not a real-world estimate |
| Safe actions | 0 postings without prior human approval | Unit tests for blocked posting |
| Risk gating | 100% of pending, transfers, income and high-value examples flagged | Unit tests using authored cases |
| Bank changes | 0 silent updates of already posted transactions | Bank-update conflict test |
| External failure | 0 blind retries after ambiguous timeout | Fake failing sink test |
| Provider sync | Incremental paging, cursor replay, removed flagging | Mocked Plaid sandbox API tests; not a live sandbox test |
| Reasoning model safety | Only approved categories; no executable model tools | Mocked `claude -p` output validation test |
| Performance | Measure p50/p95 processing time, transactions/min and memory with fixed hardware | Demo runtime in `artifacts/eval.json`; **not a load test** |
| Explainability | 100% of proposals have category, confidence, rationale, status | Generated proposals and audit rows |

## Framework

Use **Python `unittest`** for deterministic unit and fault-injection tests. Use `src/eval.py` for a small repeatable workflow scorecard. For real deployments, add end-to-end Plaid sandbox tests, an Akaunting test container and a manually audited transaction set. Have a human bookkeeper assess errors and measure reviewer acceptance, false expense classification and reconciliation accuracy.

## Guardrail rules (enforced in code)

1. Categorizer/Claude proposes; a **human explicitly approves**; only approved, settled, non-transfer expenses can post.
2. Every source transaction has a stable ID and unique constraint. Revised posted transactions are treated as reconciliation conflicts.
3. Unknown, large or pending expenses are held. An unknown expense can be approved with an explicit human category override; a transfer, pending transaction, or income cannot.
4. An external API failure enters `uncertain`; a second automatic attempt is prohibited pending manual reconciliation.
5. Claude has no file, shell, browser or bank tools; its structured output is validated and never executed.
6. Currency is restricted to USD. There is no payment initiation or automatic account linking.

## Known limits

- The rules and fake-bank fixture are designed for a demonstration. They do not establish category accuracy on real bank transactions.
- Plaid Sandbox requires credentials and an access token; production bank OAuth/Link, permissions, verified webhook signatures and consent are not included.
- Akaunting's actual write API is **not live-tested**; IDs, payment-method settings and response shapes may vary across installations.
- The HTTP service is deliberately **read-only** and bound to loopback by default; CLI authorization is based on trusted machine access.
- The default run uses **no Claude calls**. Live `claude -p` must be configured and tested in your environment; `CLAUDE_KEY` is left unchanged and is **not** interpreted as `ANTHROPIC_API_KEY`.
- For serious accounting, add immutable audit storage, accounting-period locks, account mapping, categorization corrections, chargebacks/refunds handling, internal transfer matching, multi-currency policy, receipt reconciliation, user roles and approval segregation.
