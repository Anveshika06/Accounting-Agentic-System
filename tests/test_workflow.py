import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from core import Ledger, Workflow, normalize, CategorizerAgent
from adapters import csv_transactions, PlaidSandboxBank

EXAMPLE={"transaction_id":"a1","account_id":"demo","date":"2026-10-01",
         "merchant":"Google Workspace","amount":"12.00","currency":"USD",
         "direction":"expense","pending":"false"}

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=Ledger(Path(self.tmp.name)/"ledger.sqlite")
        self.wf=Workflow(self.ledger)
    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()
    def test_idempotency_and_review(self):
        self.assertEqual(self.ledger.ingest([EXAMPLE,EXAMPLE],"test")["duplicate"],1)
        self.assertEqual(self.wf.process()["review"],1)
        self.assertEqual(self.wf.process()["skipped"],1)
        p=self.ledger.list_proposals()[0]
        self.assertEqual(p["category"],"Software")
        with self.assertRaises(ValueError):
            self.wf.post_local(p["id"])
        self.wf.approve(p["id"],"accountant")
        self.assertTrue(self.wf.post_local(p["id"]).startswith("local:"))
        self.assertEqual(len(self.wf.summary()),1)
        with self.assertRaises(ValueError):
            self.wf.post_local(p["id"])
    def test_restrictions(self):
        rows=[]
        for i,(merchant,amt,direction,pending) in enumerate([
            ("Transfer To Savings","10","expense","false"),
            ("Google Workspace","10","expense","true"),
            ("Client Income","10","income","false"),
            ("Unknown Shop","2000","expense","false")]):
            r=dict(EXAMPLE,transaction_id=str(i),merchant=merchant,amount=amt,direction=direction,pending=pending)
            rows.append(r)
        self.ledger.ingest(rows,"test");self.wf.process()
        for p in self.ledger.list_proposals():
            self.assertEqual(p["status"],"held")
        for p in self.ledger.list_proposals():
            if p["category"]=="Transfer" or p["direction"]=="income":
                with self.assertRaises(ValueError):
                    self.wf.approve(p["id"],"accountant")
    def test_modified_after_post_not_silently_changed(self):
        self.ledger.ingest([EXAMPLE],"test")
        self.wf.process()
        p=self.ledger.list_proposals()[0]
        self.wf.approve(p["id"],"accountant");self.wf.post_local(p["id"])
        updated=dict(EXAMPLE,amount="500.00")
        self.assertEqual(self.ledger.ingest([updated],"test")["conflict"],1)
        self.assertEqual(self.ledger.list_transactions()[0]["amount_cents"],1200)
    def test_bank_change_reclassifies(self):
        self.ledger.ingest([EXAMPLE],"test");self.wf.process()
        new=dict(EXAMPLE,merchant="Office Depot")
        self.assertEqual(self.ledger.ingest([new],"test")["updated"],1)
        self.wf.process()
        self.assertEqual(self.ledger.list_proposals()[0]["category"],"Office Supplies")
    def test_external_timeout_never_retried(self):
        self.ledger.ingest([EXAMPLE],"test");self.wf.process()
        tx=self.ledger.list_proposals()[0]["id"]
        self.wf.approve(tx,"accountant")
        class Broken:
            name="broken"
            def post(self,tx): raise TimeoutError("fake network timeout")
        with self.assertRaises(RuntimeError):
            self.wf.post_external(tx,Broken())
        self.assertEqual(self.ledger.list_proposals()[0]["status"],"uncertain")
        with self.assertRaises(ValueError):
            self.wf.post_external(tx,Broken())
    def test_invalid_amount(self):
        for amount in ["-1","0","nan","not money"]:
            with self.assertRaises(ValueError):
                normalize(dict(EXAMPLE,amount=amount),"bank")
    def test_plaid_paginated_sync_and_cursor_replay(self):
        with patch.dict(os.environ,{"PLAID_CLIENT_ID":"dummy","PLAID_SECRET":"dummy","PLAID_ACCESS_TOKEN":"dummy"}):
            bank=PlaidSandboxBank()
        tx={"transaction_id":"T","account_id":"A","date":"2026-10-01","name":"Uber","amount":18.5,"iso_currency_code":"USD","pending":False}
        pages=[{"added":[tx],"modified":[],"removed":[],"next_cursor":"step1","has_more":True},
               {"added":[],"modified":[],"removed":[],"next_cursor":"end","has_more":False}]
        bank.call=lambda endpoint,payload: pages.pop(0)
        out=bank.sync(self.ledger)
        self.assertEqual(out["new"],1)
        self.assertEqual(self.ledger.setting("plaid_cursor"),"end")
        bank.call=lambda endpoint,payload:{"added":[],"modified":[],"removed":[],"next_cursor":"end","has_more":False}
        self.assertEqual(bank.sync(self.ledger)["new"],0)
    def test_removed_bank_item_blocked(self):
        with patch.dict(os.environ,{"PLAID_CLIENT_ID":"dummy","PLAID_SECRET":"dummy","PLAID_ACCESS_TOKEN":"dummy"}):
            bank=PlaidSandboxBank()
        tx={"transaction_id":"T","account_id":"A","date":"2026-10-01","name":"Uber","amount":18.5,"iso_currency_code":"USD","pending":False}
        batches=iter([
            {"added":[tx],"modified":[],"removed":[],"next_cursor":"a","has_more":False},
            {"added":[],"modified":[],"removed":[{"transaction_id":"T"}],"next_cursor":"b","has_more":False}])
        bank.call=lambda *a:next(batches)
        bank.sync(self.ledger);self.wf.process()
        bank.sync(self.ledger)
        self.assertEqual(self.ledger.list_proposals()[0]["status"],"held")
        with self.assertRaises(ValueError):
            self.wf.approve(self.ledger.list_proposals()[0]["id"],"accountant")

if __name__=="__main__": unittest.main()

class ReasonerTests(unittest.TestCase):
    def test_claude_disabled_tools_and_json_validation(self):
        from core import ClaudeReviewAgent
        data=dict(EXAMPLE,amount_cents=1200)
        with patch.dict(os.environ,{"CLAUDE_KEY":"test-dummy"}):
            with patch("core.subprocess.run") as run:
                run.return_value.returncode=0
                run.return_value.stdout='{"category":"Office Supplies","confidence":0.91,"reason":"Office merchant"}'
                actual=ClaudeReviewAgent().propose(data,{"category":"Other"})
                self.assertEqual(actual["category"],"Office Supplies")
                cmd=run.call_args.args[0]
                self.assertEqual(cmd[0:2],["claude","-p"])
                self.assertIn("--tools",cmd)
                self.assertEqual(cmd[cmd.index("--tools")+1],"")
                run.return_value.stdout='{"category":"Make a wire transfer","confidence":1,"reason":"bad"}'
                with self.assertRaises(RuntimeError):
                    ClaudeReviewAgent().propose(data,{"category":"Other"})
