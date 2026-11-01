"""Open-weights drafting agent: MCP client + local Ollama model (e.g. qwen2.5:7b, llama3.1, gemma2).
Plans -> reads profile -> drafts -> proposes -> if guardrails reject, revises (max 3) -> STOPS.
It has no way to approve. Usage: python agent.py L-0042 [--age 13-15]"""
import asyncio, json, os, sys, urllib.request
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
SYS = ("You help a teacher prepare a short, plain-language summary of a learner's demonstrated "
       "strengths and struggles. Follow the drafting_rules exactly. Use only the data given. "
       "Do not invent facts. Output only the summary text.")

STUB = ""   # set per run in main() when DRAFTER=stub

def llm(messages):
    if os.environ.get("DRAFTER") == "stub":      # for tests without a model
        return STUB
    req = urllib.request.Request(f"{HOST}/api/chat", json.dumps(
        {"model": MODEL, "messages": messages, "stream": False, "options": {"temperature": 0.3}}).encode(),
        {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=300))["message"]["content"].strip()

def data(res): return json.loads(res.content[0].text)

async def main(learner, age):
    if os.environ.get("MCP_URL"):     # hosted server: MCP_URL=https://host/mcp  LP_AGENT_TOKEN=...
        link = streamablehttp_client(os.environ["MCP_URL"], headers={"Authorization": "Bearer " + os.environ["LP_AGENT_TOKEN"]})
    else:                              # local server over stdio
        link = stdio_client(StdioServerParameters(command=sys.executable, args=[os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")], env={**os.environ}))
    async with link as streams, ClientSession(streams[0], streams[1]) as s:
        await s.initialize()
        prof = data(await s.call_tool("get_profile", {"learner_id": learner, "age_band": age, "include_pending": True}))
        if not prof.get("pending_evidence"):
            print("Nothing pending: nothing to draft."); return
        global STUB
        ids = " ".join(f"[{p['id']}]" for p in prof["pending_evidence"][:3])
        STUB = (f"Recent entries add to the picture of this learner's work {ids}. "
                "What would the learner like to try more of, and where do they feel most confident?")
        msgs = [{"role": "system", "content": SYS},
                {"role": "user", "content": "Profile data:\n" + json.dumps(prof, indent=1) + "\nWrite the summary."}]
        for attempt in range(1, 4):
            text = llm(msgs)
            res = data(await s.call_tool("propose_update", {"learner_id": learner, "wording": text, "model_name": "stub" if os.environ.get("DRAFTER") == "stub" else MODEL}))
            if res.get("accepted"):
                print(f"Proposal #{res['proposal_id']} drafted and waiting for a teacher.\n{res['next']}"); return
            print(f"Attempt {attempt} rejected by guardrails: {res['problems']}")
            msgs += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Rejected: " + "; ".join(res["problems"]) + ". Revise."}]
        print("Could not produce acceptable wording; evidence stays pending. Teacher can write it by hand.")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[sys.argv.index("--age") + 1] if "--age" in sys.argv else "9-12"))
