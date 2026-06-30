"""Print every API provider/model the FormuDoc AI council supports.

Run:  python list_models.py
Reflects the live config (including any FORMUDOC_*_MODEL env vars you've set).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))
from app.services import council_engine as ce

def row(prov, endpoint, model, env, keyhint):
    print(f"  {prov:<10} | {model:<42} | env {env}")
    print(f"  {'':<10} | endpoint: {endpoint}")
    print(f"  {'':<10} | key looks like: {keyhint}")
    print("  " + "-" * 76)

print("\n=== FormuDoc — AI council: supported providers & models ===\n")
print("  Each council 'seat' = one API key. The model MUST be vision-capable")
print("  (it reads the page image). Override a model with its env var before launch.\n")

row("gemini", "generativelanguage.googleapis.com", ce._GEMINI_MODEL,
    "FORMUDOC_GEMINI_MODEL", "AIza... or AQ....")
for prov, (base, envv, default) in ce._OAI.items():
    row(prov, base, os.getenv(envv, default), envv,
        {"openai":"sk-...","openrouter":"sk-or-...","nvidia":"nvapi-...",
         "groq":"gsk_...","mistral":"(Mistral key)","github":"(GitHub PAT)"}[prov])
row("anthropic", "api.anthropic.com", ce._ANTHROPIC_MODEL,
    "FORMUDOC_ANTHROPIC_MODEL", "sk-ant-...")

print("\n=== Key auto-detection (paste the key bare, no prefix needed) ===\n")
for k in ["AIzaSyXXXX", "AQ.Ab8XXXX", "nvapi-XXXX", "gsk_XXXX",
          "sk-or-XXXX", "sk-ant-XXXX", "sk-XXXX", "some-other-key"]:
    print(f"  {k:<16} -> {ce._infer_provider(k)}")
print("\n  (You can also force a provider explicitly, e.g. 'nvidia:nvapi-XXXX'.)")
print(f"\n  API call timeout: {ce._TIMEOUT}s  (env FORMUDOC_API_TIMEOUT)\n")
