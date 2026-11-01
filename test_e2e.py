import asyncio, json, os, sys, tempfile
os.environ["LP_DB"] = tempfile.mktemp(suffix=".db")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import core

async def main():
    p = StdioServerParameters(command=sys.executable, args=["server.py"], env={**os.environ})
    async with stdio_client(p) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        print("tools:", [t.name for t in (await s.list_tools()).tools])
        call = lambda n, a: s.call_tool(n, a)
        J = lambda res: json.loads(res.content[0].text)
        for t, sc in [("2025-T1", 72), ("2025-T2", 80), ("2025-T3", 86)]:
            print(J(await call("add_evidence", dict(learner_id="L-1", term=t, subject="Mathematics", kind="quiz", teacher="Ms W", score=sc))))
        print("bad score ->", J(await call("add_evidence", dict(learner_id="L-1", term="2025-T1", subject="Maths", kind="quiz", teacher="x", score=140))))
        print("profile before approval ->", J(await call("get_profile", dict(learner_id="L-1")))["subjects"])
        print("prescriptive ->", J(await call("propose_update", dict(learner_id="L-1", wording="L-1 should become an engineer [E1].")))["problems"])
        ok = J(await call("propose_update", dict(learner_id="L-1", wording="Maths results rise across three terms [E1] [E2] [E3]. What does the learner enjoy most about it?", model_name="test")))
        print("proposal ->", ok["accepted"], ok["diff"])
        core.approve(ok["proposal_id"], "Ms Wanjiru")           # the human step
        pr = J(await call("get_profile", dict(learner_id="L-1")))
        print("profile after approval ->", pr["subjects"], pr["approved_summary"]["approved_by"])
asyncio.run(main())
