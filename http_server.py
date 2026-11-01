"""Hosted mode: the MCP server over streamable HTTP plus the teacher web app.
  /mcp      agents and MCP clients       Authorization: Bearer <LP_AGENT_TOKEN>
  /         teacher web app              HTTP Basic: per-teacher accounts stored in the database (python manage.py add-teacher)
  /health   uptime check
Agents hold only the bearer token; they have no teacher account, so they cannot approve anything.
Run:  LP_AGENT_TOKEN=<16+ chars> python http_server.py   (uses $PORT, default 8000)"""
import hmac, os, sys
os.environ.setdefault("LP_STRICT", "1")           # deployments require registered learners with guardian consent
import uvicorn
from starlette.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings
import core
from server import mcp

AGENT = os.environ.get("LP_AGENT_TOKEN", "")
if len(AGENT) < 16: sys.exit("Set LP_AGENT_TOKEN (16+ characters). Refusing to start unauthenticated.")
mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)  # every route is authenticated
app = mcp.streamable_http_app()

class AgentAuth:                                   # pure ASGI so streaming responses are untouched
    def __init__(self, a): self.a = a
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            got = dict(scope["headers"]).get(b"authorization", b"").decode()
            if not hmac.compare_digest(got, f"Bearer {AGENT}"):
                return await JSONResponse({"error": "unauthorized"}, 401, {"WWW-Authenticate": "Bearer"})(scope, receive, send)
        await self.a(scope, receive, send)
app.add_middleware(AgentAuth)
async def health(req): return JSONResponse({"ok": True})
app.add_route("/health", health)
import web
web.register(app)

if __name__ == "__main__":
    if not core.conn().execute("SELECT 1 FROM teachers").fetchone(): print("Note: no teacher accounts yet. Create one: python manage.py add-teacher \"Your Name\" --class <ID>")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
