"""Local-only read-only HTTP interface; actions are CLI-only for the demo.

Production access must go through HTTPS+auth reverse proxy with a service identity.
"""
import json
import os
from http.server import BaseHTTPRequestHandler,HTTPServer


def serve(ledger,workflow,host,port):
    token=os.environ.get("APP_TOKEN","")
    if len(token)<24:
        raise ValueError("APP_TOKEN of 24+ characters required for API")
    if host not in ("127.0.0.1","localhost","::1") and os.environ.get("ALLOW_CONTAINER_BIND")!="1":
        raise ValueError("Non-loopback bind blocked; only enable behind a localhost-mapped container port")
    class Handler(BaseHTTPRequestHandler):
        def get(self,status,data):
            raw=json.dumps(data,default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if self.path=="/health":
                return self.get(200,{"status":"ok"})
            if self.headers.get("Authorization")!="Bearer "+token:
                return self.get(401,{"error":"unauthorized"})
            if self.path=="/proposals":
                return self.get(200,workflow.l.list_proposals())
            if self.path=="/report":
                return self.get(200,workflow.summary())
            if self.path=="/transactions":
                return self.get(200,ledger.list_transactions())
            self.get(404,{"error":"not found"})
        def do_POST(self):
            self.get(405,{"error":"Use the explicit approval CLI; write operations unavailable via HTTP"})
    print(f"Listening on http://{host}:{port} (read-only, token required)")
    HTTPServer((host,port),Handler).serve_forever()
