"""Replays the last step of the failed Task through the Inference API.

The Task failed with "no_answer" right after the agent wrote its answer to a file.
Here the model gets the same situation (two page visits, then write -> "ok") and we
count what its next turn is: a text answer, an empty reply, a tool call, or tool syntax in text.
A text answer counts as correct only if it contains all 8 expected values.

Usage: python scripts/glm_final_step.py [runs_per_model]   (default 15)
Log: logs/glm_final_step_<time>.json
"""
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv(".env")
URL = "https://inference.moss.dev/v1/chat/completions"
AUTH = {"Authorization": f"Bearer {os.environ['MOSS_PROJECT_ID']}:{os.environ['MOSS_PROJECT_KEY']}"}
RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 15
CONFIGS = [("z-ai/glm-5.3", None), ("z-ai/glm-5.3", "medium"), ("anthropic/claude-haiku-5.5", None)]

TOOLS = [
    {"type": "function", "function": {"name": "browser_execute", "description": "Open a URL and return the page text.",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {"name": "write", "description": "Write a file to the outputs/ folder.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
]
RRR_PAGE = ("RRR (film) - Wikipedia. Infobox: Directed by S. S. Rajamouli. Release date 25 March 2022. "
            "Running time 182 minutes. Language Telugu. Music by M. M. Keeravani.")
SONG_PAGE = ("Naatu Naatu - Wikipedia. Infobox: Song by Rahul Sipligunj and Kaala Bhairava from the album RRR. Released 10 November 2021. "
             "Length 3:36. Composer M. M. Keeravani. Lyricist Chandrabose. 'Naatu Naatu' became the first Indian song to win "
             "the Academy Award for Best Original Song.")
ANSWER = "RRR; S. S. Rajamouli; 2022-03-25; 182; Naatu Naatu; M. M. Keeravani; Chandrabose; 3:36"


def tool_call(i, name, args):
    return {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


MESSAGES = [
    {"role": "system", "content": "You are a browser agent. Use tools to reach the goal. When done, reply to the user with the final answer."},
    {"role": "user", "content": "Using Wikipedia, find the Indian (Telugu-language) film whose song won the Academy Award for Best Original Song. "
                                "Report: film title, director, release date (YYYY-MM-DD), runtime in minutes, song title, composer, lyricist, song length (m:ss)."},
    {"role": "assistant", "content": "", "tool_calls": [tool_call(1, "browser_execute", {"url": "https://en.wikipedia.org/wiki/RRR"})]},
    {"role": "tool", "tool_call_id": "call_1", "content": RRR_PAGE},
    {"role": "assistant", "content": "Film page confirms: RRR, S. S. Rajamouli, 25 March 2022, 182 minutes, Telugu. Now the song page.",
     "tool_calls": [tool_call(2, "browser_execute", {"url": "https://en.wikipedia.org/wiki/Naatu_Naatu"})]},
    {"role": "tool", "tool_call_id": "call_2", "content": SONG_PAGE},
    {"role": "assistant", "content": "All values confirmed. Saving evidence.",
     "tool_calls": [tool_call(3, "write", {"path": "outputs/naatu_naatu_film.md", "content": ANSWER})]},
    # tool result text copied from the real failed task (its file was 1092 bytes)
    {"role": "tool", "tool_call_id": "call_3", "content": "ok: wrote outputs/naatu_naatu_film.md (1092 bytes)"},
]
EXPECTED = ["RRR", "Rajamouli", "2022-03-25", "182", "Naatu Naatu", "Keeravani", "Chandrabose", "3:36"]
TOOL_SYNTAX_IN_TEXT = re.compile(r"<tool_call>|<\|?tool|\"name\"\s*:\s*\"(write|browser_execute)\"", re.I)


def classify(choice):
    msg = choice["message"]
    text = (msg.get("content") or "").strip()
    if msg.get("tool_calls"):
        return "tool_call:" + ",".join(t["function"]["name"] for t in msg["tool_calls"])
    if not text:
        return f"EMPTY(finish={choice.get('finish_reason')})"
    if TOOL_SYNTAX_IN_TEXT.search(text):
        return "MALFORMED(tool syntax in text)"
    return "text_answer"


def main():
    client = httpx.Client(headers=AUTH, timeout=120)
    rows = []
    for model, effort in CONFIGS:
        counts = Counter()
        for i in range(RUNS):
            body = {"model": model, "messages": MESSAGES, "tools": TOOLS}
            if effort:
                body["reasoning_effort"] = effort
            r = client.post(URL, json=body)
            if r.is_success:
                choice = r.json()["choices"][0]
                kind = classify(choice)
                content = choice["message"].get("content") or ""
                row = {"finish_reason": choice.get("finish_reason"), "content": content,
                       "correct": kind == "text_answer" and all(v in content for v in EXPECTED),
                       "tool_calls": choice["message"].get("tool_calls"), "usage": r.json().get("usage")}
            else:
                kind, row = f"HTTP {r.status_code}", {"error": r.text[:300]}
            counts[kind + (" (correct)" if row.get("correct") else "")] += 1
            rows.append({"model": model, "effort": effort, "i": i, "kind": kind, **row})
        print(f"{model} effort={effort}: {dict(counts)}", flush=True)
    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.makedirs("logs", exist_ok=True)
    path = f"logs/glm_final_step_{run}.json"
    json.dump({"run": run, "n": RUNS, "rows": rows}, open(path, "w"), indent=2)
    print("log:", path)


main()
