"""Bank/source and ledger/sink adapters; swap adapters without changing the workflow."""
import base64
import csv
import json
import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def csv_transactions(path):
    with open(path,newline="",encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _post_json(url, body, headers=None):
    data=json.dumps(body).encode("utf-8")
    req=Request(url,data=data,method="POST",headers={"Content-Type":"application/json",**(headers or {})})
    with urlopen(req,timeout=18) as res:
        return json.loads(res.read().decode("utf-8"))


class PlaidSandboxBank:
    """Real Plaid Sandbox integration using Transactions Sync (no production bank access)."""
    def __init__(self):
        self.client_id=os.environ["PLAID_CLIENT_ID"]
        self.secret=os.environ["PLAID_SECRET"]
        self.access_token=os.environ["PLAID_ACCESS_TOKEN"]
        self.base="https://sandbox.plaid.com"

    def call(self, endpoint, body):
        return _post_json(self.base+endpoint,{"client_id":self.client_id,"secret":self.secret,**body})

    @staticmethod
    def _convert(tx):
        # Plaid: positive amount = debit; negative amount = credit.
        amount=Decimal(str(tx["amount"]))
        if amount==0:
            raise ValueError("Zero amount from bank")
        return {"transaction_id":tx["transaction_id"],"account_id":tx["account_id"],
                "date":tx.get("date") or tx.get("authorized_date"),
                "merchant":tx.get("merchant_name") or tx.get("name") or "Unknown",
                "amount":str(abs(amount)), "currency":tx.get("iso_currency_code") or "USD",
                "direction":"expense" if amount>0 else "income", "pending":bool(tx.get("pending",False))}

    def sync(self, ledger):
        """Fetch ALL pages before mutating local data/cursor; replay safe after crash.

        Mutation during pagination -> restart from original stored cursor.
        Modified/removed records are flagged; posted records are never silently rewritten.
        """
        original_cursor=ledger.setting("plaid_cursor")
        for attempt in range(3):
            cursor=original_cursor
            batches={"added":[],"modified":[],"removed":[]}
            try:
                for _ in range(100):
                    payload={"access_token":self.access_token,"count":500}
                    if cursor:
                        payload["cursor"]=cursor
                    page=self.call("/transactions/sync",payload)
                    for kind in batches:
                        batches[kind].extend(page.get(kind,[]))
                    cursor=page.get("next_cursor",cursor)
                    if not page.get("has_more",False):
                        break
                else:
                    raise RuntimeError("Sync exceeded 100 pages")
                break
            except HTTPError as e:
                detail=e.read().decode("utf-8",errors="replace")[:1500]
                if "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION" in detail and attempt<2:
                    continue
                raise RuntimeError("Plaid sandbox sync failed") from e
        rows=[self._convert(t) for t in batches["added"]+batches["modified"]]
        # apply changed transactions and cursor atomically
        with ledger.db:
            stats=ledger.ingest(rows,"plaid-sandbox",within_transaction=True)
            for removed in batches["removed"]:
                ext=removed.get("transaction_id")
                row=ledger.db.execute("SELECT id FROM transactions WHERE source=? AND external_id=?",
                                      ("plaid-sandbox",ext)).fetchone()
                if row:
                    ledger.db.execute("UPDATE transactions SET removed=1 WHERE id=?",(row["id"],))
                    ledger.db.execute("UPDATE proposals SET status='held',updated=datetime('now') WHERE tx_id=? AND status IN ('review','approved')",(row["id"],))
                    ledger.audit(row["id"],"bank_removed",{"manual_reconciliation_required":True})
            if cursor:
                ledger.set_setting("plaid_cursor",cursor)
        stats["removed_flags"]=len(batches["removed"])
        return stats


class AkauntingSink:
    """Explicit, approval-gated Akaunting transaction sink.

    Requires an existing account + category IDs, company API credentials, and
    a configured HTTPS endpoint. Validate field mapping against your deployment.
    """
    name="akaunting"
    def __init__(self):
        self.base=os.environ["AKAUNTING_BASE_URL"].rstrip("/")
        parsed=urlparse(self.base)
        if parsed.scheme!="https" and parsed.hostname not in ("localhost","127.0.0.1"):
            raise ValueError("Akaunting requires HTTPS except local loopback")
        self.email=os.environ["AKAUNTING_EMAIL"]
        self.password=os.environ["AKAUNTING_PASSWORD"]
        self.account_id=int(os.environ["AKAUNTING_ACCOUNT_ID"])
        self.categories=json.loads(os.environ["AKAUNTING_CATEGORY_IDS_JSON"])
        self.company_id=int(os.environ["AKAUNTING_COMPANY_ID"])

    def payload(self, tx):
        category=self.categories.get(tx["category"])
        if not category:
            raise ValueError("No Akaunting category ID for "+tx["category"])
        return {"company_id":self.company_id,"type":"expense",
                "number":"BANK-"+tx["id"], "account_id":self.account_id,
                "paid_at":tx["date"]+" 12:00:00","amount":str(Decimal(tx["amount_cents"])/100),
                "currency_code":tx["currency"],"currency_rate":1,
                "category_id":int(category),"payment_method":"other",
                "description":tx["merchant"]}

    def post(self, tx):
        body=self.payload(tx)
        token=base64.b64encode((self.email+":"+self.password).encode()).decode()
        output=_post_json(self.base+"/api/transactions",body,
                         {"Authorization":"Basic "+token,"Accept":"application/json"})
        # Some installations wrap the resource in `data`.
        resource=output.get("data",output)
        ref=resource.get("id")
        if not ref:
            raise RuntimeError("Akaunting did not return a transaction ID")
        return "akaunting:"+str(ref)
