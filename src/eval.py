"""Small reproducible eval harness; not a real-bank performance claim."""
import json
import statistics
import tempfile
import time
from contextlib import closing
from pathlib import Path
from core import Ledger, Workflow, CategorizerAgent

cases = [
    ("Google Workspace", "Software"), ("Cloud Hosting", "Software"),
    ("Office Depot", "Office Supplies"), ("Staples Printer", "Office Supplies"),
    ("Uber Ride", "Travel"), ("Delta Airline", "Travel"),
    ("Cafe Downtown", "Meals"), ("Restaurant", "Meals"),
    ("Electric Bill", "Utilities"), ("Transfer Savings", "Transfer"),
    ("Unfamiliar Merchant", "Other")
]


def main():
    start = time.perf_counter()
    agent = CategorizerAgent()
    # Microbenchmark rules-only inference; exclude SQLite and file I/O.
    samples = []
    for i in range(1000):
        t = time.perf_counter()
        agent.propose({"merchant": cases[i % len(cases)][0]})
        samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    predicted = [agent.propose({"merchant": name})["category"] for name, _ in cases]
    accuracy = sum(a == b for a, (_, b) in zip(predicted, cases)) / len(cases)

    with tempfile.TemporaryDirectory() as tmp:
        ledger = Ledger(Path(tmp) / "ledger.sqlite")
        # Closing sqlite3 connection before TemporaryDirectory cleanup is
        # required on Windows (otherwise WinError 32: file in use).
        with closing(ledger.db):
            data = [
                {"transaction_id": str(i), "account_id": "test",
                 "date": "2026-10-01", "merchant": merchant,
                 "amount": "15.00", "currency": "USD",
                 "direction": "expense", "pending": False}
                for i, (merchant, _) in enumerate(cases)
            ]
            ledger.ingest(data, "eval")
            repeats = ledger.ingest(data, "eval")
            Workflow(ledger).process()
            pending_reviews = len(ledger.list_proposals())
            blocked = all(p["status"] != "posted" for p in ledger.list_proposals())
            audits = ledger.db.execute("SELECT COUNT(*) FROM audits").fetchone()[0]

            report = {
                "dataset": "11 authored test cases (not real-bank accuracy)",
                "category_accuracy": accuracy,
                "duplicate_detection": repeats["duplicate"] == len(cases),
                "no_unapproved_posts": blocked,
                "proposals": pending_reviews,
                "audit_events": audits,
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
                "categorizer_p50_ms": round(samples[499], 5),
                "categorizer_p95_ms": round(samples[949], 5),
                "guardrail_checks": "unittest discover -s tests"
            }

    # The database is closed before the temporary directory is deleted.
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/eval.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
