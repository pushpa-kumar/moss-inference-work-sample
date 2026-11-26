"""Inference API checks.

  latency  - time to first token per model (streamed, 5 runs, unique prompt each time)
  overhead - same question with and without an index: what retrieval adds
  rag      - answers from the index, and what happens when the answer is not in it
  compat   - OpenAI SDK, /responses, tool calling, JSON schema output
  errors   - bad model, missing index, wrong key, unknown field, empty input

Every prompt gets a random tag, because identical requests are served from a response cache.
Logs: logs/inference_<time>/<section>.jsonl and summary.md
"""
import json
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(".env")
BASE = "https://inference.moss.dev/v1"
PID, KEY = os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"]
OUT = Path("logs") / f"inference_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
OUT.mkdir(parents=True, exist_ok=True)
http = httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {PID}:{KEY}"}, timeout=120)
SUMMARY = []


def log(section, row):
    with open(OUT / f"{section}.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")


def say(line=""):
    print(line, flush=True)
    SUMMARY.append(line)


def json_or_text(r):
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text[:300]}


def error_message(status, body):
    if status < 400:
        return "(no error, it answered)"
    err = body.get("error", body) if isinstance(body, dict) else body
    return str(err.get("message", err) if isinstance(err, dict) else err)


def tag(text):
    return f"{text} (ref {os.urandom(4).hex()})"


def chat(messages, index=None, auth=None, **body):
    headers = {}
    if index:
        headers["X-Moss-Indexes"] = index
    if auth:
        headers["Authorization"] = auth
    body = {"model": "moss/fastlane-1", "max_tokens": 250, "messages": messages, **body}
    r = http.post("/chat/completions", json=body, headers=headers)
    row = {"request": {"index": index, **body}, "status": r.status_code,
           "retrieve_ms": r.headers.get("x-moss-retrieve-ms"), "body": json_or_text(r)}
    if r.is_success:
        msg = row["body"]["choices"][0]["message"]
        row["text"], row["tool_calls"] = msg.get("content") or "", msg.get("tool_calls")
    return row


def stream(prompt, model="moss/fastlane-1", index=None, max_tokens=150):
    """Returns time to first token, total time, text and usage for one streamed request."""
    body = {"model": model, "max_tokens": max_tokens, "stream": True, "stream_options": {"include_usage": True},
            "messages": [{"role": "user", "content": prompt}]}
    t0, ttft, text, usage = time.perf_counter(), None, "", None
    with http.stream("POST", "/chat/completions", json=body, headers={"X-Moss-Indexes": index} if index else {}) as r:
        retrieve_ms = r.headers.get("x-moss-retrieve-ms")
        for line in r.iter_lines():
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            event = json.loads(line[5:])
            usage = event.get("usage") or usage
            for choice in event.get("choices", []):
                piece = (choice.get("delta") or {}).get("content")
                if piece:
                    ttft = ttft or (time.perf_counter() - t0) * 1000
                    text += piece
    return {"model": model, "index": index, "prompt": prompt, "status": r.status_code, "retrieve_ms": retrieve_ms,
            "ttft_ms": round(ttft) if ttft else None, "total_ms": round((time.perf_counter() - t0) * 1000),
            "usage": usage, "text": text}


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values)) if values else None


def latency():
    say("## Latency (no index, 5 runs, max 80 tokens; first token = first visible text, so reasoning time is included)\n\n| model | first token median | min-max | total median | non-empty |\n|---|---|---|---|---|")
    for model in ["moss/fastlane-1", "openai/gpt-6-luna", "anthropic/claude-haiku-5.5", "google/gemini-3.5-flash-lite", "z-ai/glm-5.3"]:
        rows = [stream(tag("In two sentences, what is single sign-on?"), model, max_tokens=80) for _ in range(5)]
        for row in rows:
            log("latency", row)
        ttfts = [r["ttft_ms"] for r in rows if r["ttft_ms"]]
        span = f"{min(ttfts)}-{max(ttfts)} ms" if ttfts else "-"
        say(f"| {model} | {median(ttfts)} ms | {span} | {median([r['total_ms'] for r in rows if r['ttft_ms']])} ms | {len(ttfts)}/5 |")


def overhead():
    say("\n## Retrieval overhead (moss/fastlane-1, 'how to setup okta sso', 5 runs)\n\n"
        "| index | first token median | retrieve ms median | prompt tokens | total median |\n|---|---|---|---|---|")
    for index in [None, "agent-memory-context"]:
        rows = [stream(tag("how to setup okta sso"), index=index) for _ in range(5)]
        for row in rows:
            log("overhead", row)
        retrieve = [float(r["retrieve_ms"]) for r in rows if r["retrieve_ms"]]
        say(f"| {index or 'none'} | {median([r['ttft_ms'] for r in rows])} ms | {median(retrieve) if retrieve else '-'} | "
            f"{(rows[0]['usage'] or {}).get('prompt_tokens')} | {median([r['total_ms'] for r in rows])} ms |")


def rag():
    say("\n## RAG (moss/fastlane-1)\n\n| question | index | expected | found |\n|---|---|---|---|")
    dont_know = ["do not have", "don't have", "do not know", "don't know", "no information"]
    cases = [
        ("Where do I set the default role for new teammates who join via SSO?", "agent-memory-context", ["settings > security"]),
        ("How long does a refund take after my return is received?", "demo-customer_faqs", ["5-7"]),
        ("Is there a fee if I return opened electronics?", "demo-customer_faqs", ["15%"]),
        ("how to setup okta sso", "demo-customer_faqs", dont_know),  # no SSO docs in this index
        ("What is the name of your company's CEO?", "demo-customer_faqs", dont_know),
    ]
    for question, index, expected in cases:
        row = chat([{"role": "user", "content": tag(question)}], index=index)
        text = row.get("text", "").lower().replace("–", "-").replace("’", "'")
        row["found"] = any(e in text for e in expected)
        log("rag", row)
        say(f"| {question} | {index} | {' / '.join(expected[:2])} | {'yes' if row['found'] else 'NO'} |")


def compat():
    say("\n## Compatibility\n\n| check | result |\n|---|---|")
    sdk = OpenAI(base_url=BASE, api_key=f"{PID}:{KEY}")
    reply = sdk.chat.completions.create(model="moss/fastlane-1", max_tokens=20, messages=[{"role": "user", "content": tag("Say hello.")}],
                                        extra_headers={"X-Moss-Indexes": "agent-memory-context"})
    log("compat", {"check": "openai sdk", "text": reply.choices[0].message.content})
    say(f"| OpenAI SDK + index header | {reply.choices[0].message.content!r} |")

    r = http.post("/responses", json={"model": "moss/fastlane-1", "input": tag("Say hello."), "max_output_tokens": 20})
    body = json_or_text(r)
    log("compat", {"check": "responses", "status": r.status_code, "body": body})
    text = "".join(part.get("text", "") for item in body.get("output", []) for part in item.get("content") or [])
    say(f"| /responses | {r.status_code} {text!r} |")

    tools = [{"type": "function", "function": {"name": "get_order_status", "description": "Look up an order by number.",
              "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}}]
    row = chat([{"role": "user", "content": tag("Where is my order 4471?")}], tools=tools)
    log("compat", {"check": "tool calling", **row})
    call = (row.get("tool_calls") or [{}])[0].get("function", {})
    say(f"| tool calling | {call.get('name')}({call.get('arguments')}) |")

    schema = {"type": "json_schema", "json_schema": {"name": "ticket", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["intent", "order_id"],
        "properties": {"intent": {"type": "string", "enum": ["refund", "track", "cancel", "other"]}, "order_id": {"type": "string"}}}}}
    row = chat([{"role": "user", "content": tag("I want my money back for order 9921, it arrived broken.")}], response_format=schema)
    log("compat", {"check": "json schema", **row})
    say(f"| JSON schema output | {' '.join(row.get('text', '').split())} |")


def errors():
    say("\n## Errors\n\n| case | status | message |\n|---|---|---|")
    hi = [{"role": "user", "content": "hi"}]
    cases = [
        ("unknown model", dict(model="moss/does-not-exist")),
        ("index that does not exist", dict(index="no-such-index-xyz")),
        ("wrong API key", dict(auth=f"Bearer {PID}:moss_wrongkey000")),
        ("key without colon", dict(auth="Bearer justonestring")),
        ("unknown field (chat/completions)", dict(banana=1)),
        ("negative max_tokens", dict(max_tokens=-5)),
    ]
    for label, kwargs in cases:
        row = chat(hi, **kwargs)
        log("errors", {"case": label, **row})
        say(f"| {label} | {row['status']} | {error_message(row['status'], row['body'])[:110]} |")
    r = http.post("/responses", json={"model": "moss/fastlane-1", "input": "hi", "banana": 1})
    body = json_or_text(r)
    log("errors", {"case": "unknown field (responses)", "status": r.status_code, "body": body})
    say(f"| unknown field (responses) | {r.status_code} | {error_message(r.status_code, body)[:110]} |")


try:
    for section in (latency, overhead, rag, compat, errors):
        section()
finally:
    (OUT / "summary.md").write_text("\n".join(SUMMARY) + "\n")
    print("logs:", OUT)
