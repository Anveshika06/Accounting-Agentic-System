"""Command-line entry point: action workflow with optional Claude reasoning."""
import argparse
import json
import os
import sys
from pathlib import Path

from core import Ledger, Workflow
from adapters import PlaidSandboxBank, AkauntingSink, csv_transactions
from hooks import load_adapter

ROOT=Path(__file__).resolve().parent.parent

def pretty(obj):
    print(json.dumps(obj,indent=2,ensure_ascii=False))


def run(args):
    l=Ledger(args.db)
    flow=Workflow(l)
    if args.cmd=="demo":
        stats=l.ingest(csv_transactions(ROOT / "src" / "data" / "sample_bank.csv"),"csv-demo")
        proposed=flow.process(reasoner=args.reasoner)
        pretty({"mode":"safe local demo", "ingestion":stats,"agent_decisions":proposed,
                "proposals":flow.l.list_proposals(),"posted_expenses":flow.summary(),"exceptions":flow.reconciler.exceptions(l)})
    elif args.cmd=="sync":
        if args.plugin:
            pretty(load_adapter(args.plugin).sync(l))
        elif args.source=="plaid":
            pretty(PlaidSandboxBank().sync(l))
        else:
            pretty(l.ingest(csv_transactions(args.file),"csv:"+args.account_alias))
    elif args.cmd=="process":
        pretty(flow.process(args.reasoner))
    elif args.cmd=="review":
        pretty(flow.l.list_proposals(status=args.status))
    elif args.cmd=="approve":
        flow.approve(args.id,args.reviewer,args.category)
        pretty({"approved":args.id,"reviewer":args.reviewer})
    elif args.cmd=="post":
        if args.sink=="local":
            ref=flow.post_local(args.id)
        else:
            if not args.confirm_external:
                raise ValueError("External posting requires --confirm-external")
            ref=flow.post_external(args.id,load_adapter(args.plugin) if args.plugin else AkauntingSink())
        pretty({"posted":args.id,"reference":ref})
    elif args.cmd=="report":
        pretty({"posted_summary":flow.summary(),"proposals":flow.l.list_proposals(),
                "exceptions":flow.reconciler.exceptions(l)})
    elif args.cmd=="audit":
        pretty([dict(r) for r in l.db.execute("SELECT * FROM audits ORDER BY id")])
    elif args.cmd=="serve":
        from server import serve
        serve(l,flow,args.host,args.port)


def parser():
    p=argparse.ArgumentParser(description="Local multi-agent accounting workflow")
    p.add_argument("--db",default=str(ROOT/"artifacts"/"ledger.sqlite"),help="SQLite location")
    sub=p.add_subparsers(dest="cmd",required=True)
    demo=sub.add_parser("demo",help="Import sample and create review proposals")
    demo.add_argument("--reasoner",choices=["rules","claude"],default="rules")
    sync=sub.add_parser("sync",help="Ingest a CSV or Plaid sandbox")
    sync.add_argument("--source",choices=["csv","plaid"],default="csv")
    sync.add_argument("--plugin",help="Trusted custom adapter module:Class")
    sync.add_argument("--file",default=str(ROOT/"data"/"sample_bank.csv"))
    sync.add_argument("--account-alias",default="local")
    proc=sub.add_parser("process",help="Classify unprocessed transactions")
    proc.add_argument("--reasoner",choices=["rules","claude"],default="rules")
    review=sub.add_parser("review")
    review.add_argument("--status",choices=["review","held","approved","posted","uncertain"])
    approve=sub.add_parser("approve",help="Explicit approval by a person")
    approve.add_argument("--id",required=True)
    approve.add_argument("--reviewer",required=True)
    approve.add_argument("--category",choices=["Software","Office Supplies","Travel","Meals","Utilities","Other"])
    post=sub.add_parser("post",help="Record approved expense in ledger")
    post.add_argument("--id",required=True)
    post.add_argument("--sink",choices=["local","akaunting"],default="local")
    post.add_argument("--confirm-external",action="store_true")
    post.add_argument("--plugin",help="Trusted custom sink module:Class; requires --confirm-external")
    sub.add_parser("report")
    sub.add_parser("audit")
    serve=sub.add_parser("serve",help="Local HTTP read-only API, token required")
    serve.add_argument("--host",default="127.0.0.1")
    serve.add_argument("--port",type=int,default=8765)
    return p

if __name__=="__main__":
    try:
        run(parser().parse_args())
    except (ValueError,RuntimeError,KeyError,FileNotFoundError) as e:
        print("ERROR:",e,file=sys.stderr)
        sys.exit(1)
