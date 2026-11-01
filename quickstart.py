"""One command:  python quickstart.py   -> venv, install, fictional demo school, drafted proposal, then the web app.
Options: --no-serve  (set up only)"""
import os, pathlib, secrets, subprocess, sys, urllib.request, venv, webbrowser
root = pathlib.Path(__file__).resolve().parent; vdir = root / ".venv"
py = vdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
def run(*a, env=None): subprocess.run([str(x) for x in a], check=True, cwd=root, env=env)
if not py.exists(): print("1/5 Creating virtual environment..."); venv.create(vdir, with_pip=True)
print("2/5 Installing dependencies..."); run(py, "-m", "pip", "install", "-q", "-r", "requirements.txt")
env = dict(os.environ, LP_DB=str(root / "demo.db"), LP_AGENT_TOKEN=secrets.token_hex(16), PORT=os.environ.get("PORT", "8000"))
print("3/5 Loading the FICTIONAL demo school (16 learners, 6 terms of marks)..."); run(py, "demo_school.py", env=env)
host = env.get("OLLAMA_HOST", "http://localhost:11434")
try: urllib.request.urlopen(host + "/api/tags", timeout=1); using = f"your local model ({env.get('OLLAMA_MODEL', 'qwen2.5:7b')})"
except Exception: env["DRAFTER"] = "stub"; using = "a built-in stub (no Ollama found; install it for a real open-weights model)"
print(f"4/5 The agent drafts a summary for learner L-6B-03 using {using}..."); run(py, "agent.py", "L-6B-03", env=env)
url = f"http://localhost:{env['PORT']}"
print(f"\n5/5 Teacher web app: {url}\n    Log in as  Ms Wanjiru  (password demo-pass-1234)  to see Grade 6 Blue. Try 'Head Teacher' to see everything.\n    Press Ctrl+C to stop.")
if "--no-serve" not in sys.argv:
    try: webbrowser.open(url)
    except Exception: pass
    try: run(py, "http_server.py", env=env)
    except KeyboardInterrupt: pass
