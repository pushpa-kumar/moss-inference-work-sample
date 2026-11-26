"""Run a Moss Task end to end and save everything it produced.

Usage:
  python scripts/run_task.py tasks/01_books_travel.json [--model z-ai/glm-5.3] [--no-schema]
                             [--effort medium] [--max-cost 0.10] [--no-start-url] [--label name]

Creates the task, polls until it reaches a terminal state, then saves to
logs/tasks/<task_id>/: request.json, task.json, trace.json, files.json, files/...
If <task>.expected.json exists, compares the structured result to it field by
field and writes compare.json. Fields are only counted from the answer itself,
never from pages the agent read.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(".env")
BASE = "https://inference.moss.dev/v1"
AUTH = {"Authorization": f"Bearer {os.environ['MOSS_PROJECT_ID']}:{os.environ['MOSS_PROJECT_KEY']}"}
TERMINAL = {"completed", "failed", "cancelled"}


def norm(v) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def compare(expected: dict, got: dict | None) -> dict:
    """Field-by-field match against the structured result. Missing result = no match."""
    got = got or {}
    return {k: {"expected": v, "got": got.get(k), "match": k in got and norm(got[k]) == norm(v)}
            for k, v in expected.items() if not k.startswith("_")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_file")
    ap.add_argument("--model")
    ap.add_argument("--effort")
    ap.add_argument("--max-cost", type=float)
    ap.add_argument("--no-schema", action="store_true")
    ap.add_argument("--no-start-url", action="store_true")
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    body = json.loads(Path(a.task_file).read_text())
    if a.model:
        body["model"] = a.model
    if a.effort:
        body["effort"] = a.effort
    if a.max_cost is not None:
        body.setdefault("limits", {})["max_cost_usd"] = a.max_cost
    if a.no_schema:
        body.pop("output_schema", None)
    if a.no_start_url:
        body.get("environment", {}).pop("start_url", None)
    body.setdefault("metadata", {})["label"] = a.label

    c = httpx.Client(base_url=BASE, headers=AUTH, timeout=60)
    t0 = time.time()
    r = c.post("/tasks", json=body)
    if not r.is_success:
        print(f"create failed: {r.status_code} {r.text}")
        sys.exit(1)
    task = r.json()
    tid = task["id"]
    d = Path("logs/tasks") / tid
    (d / "files").mkdir(parents=True, exist_ok=True)
    (d / "request.json").write_text(json.dumps({"label": a.label, "body": body}, indent=2))
    print(f"[{a.label}] created {tid} status={task['status']}", flush=True)

    while task["status"] not in TERMINAL:
        time.sleep(3)
        r = c.get(f"/tasks/{tid}")
        r.raise_for_status()
        task = r.json()
    wall = round(time.time() - t0, 1)
    (d / "task.json").write_text(json.dumps(task, indent=2))

    tr = c.get(f"/tasks/{tid}/trace")
    trace = tr.json() if tr.is_success else {"http": tr.status_code, "body": tr.text}
    (d / "trace.json").write_text(json.dumps(trace, indent=2))

    files = c.get(f"/tasks/{tid}/files").json().get("data", [])
    (d / "files.json").write_text(json.dumps(files, indent=2))
    for f in files:
        if f["path"].startswith("outputs/"):
            r = c.get(f"/tasks/{tid}/files/{f['path']}")
            r.raise_for_status()
            p = d / "files" / f["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(r.content)

    result = task.get("result") or {}
    structured = result.get("output") if isinstance(result.get("output"), dict) else None
    if structured is None and result.get("output_text"):
        try:
            structured = json.loads(result["output_text"])
        except (json.JSONDecodeError, TypeError):
            pass

    summary = {
        "label": a.label, "task_id": tid, "model": task.get("model"), "effort": task.get("effort"),
        "schema": "output_schema" in body, "status": task["status"], "error": task.get("error"),
        "verification": task.get("verification"), "wall_s": wall,
        "usage_steps": task.get("usage", {}).get("steps"), "trace_steps": trace.get("steps"),
        "cost_usd": task.get("usage", {}).get("cost", {}).get("total_usd"),
        "has_result": bool(task.get("result")), "output_files": [f["path"] for f in files if f["path"].startswith("outputs/")],
    }
    exp_path = Path(a.task_file).with_suffix(".expected.json")
    if exp_path.exists():
        cmp_ = compare(json.loads(exp_path.read_text()), structured)
        (d / "compare.json").write_text(json.dumps(cmp_, indent=2))
        summary["fields_correct"] = sum(v["match"] for v in cmp_.values())
        summary["fields_total"] = len(cmp_)
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
