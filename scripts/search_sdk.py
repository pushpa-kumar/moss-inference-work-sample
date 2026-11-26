"""Search SDK checks behind the "Ideas on how Moss works" section.

1. Staleness: a loaded copy of a cloud index does not see a cloud update until
   load_index() is called again, or the auto_refresh poller runs.
2. Size: load_index() downloads the whole index; load time and on-disk size grow with doc count.

Creates temporary indexes (prefix "test-") and deletes them. Log: logs/search_sdk_<time>.json
"""
import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from moss import DocumentInfo, MossClient, QueryOptions

load_dotenv(".env")
PID, KEY = os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"]
RUN = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG = []


def log(step, **data):
    LOG.append({"step": step, **data})
    print(step, data, flush=True)


async def has_doc(client, index, doc_id):
    # keyword-only search (alpha=0) so the check does not depend on embeddings
    res = await client.query(index, "zebra stripe discount nonprofits", QueryOptions(top_k=3, alpha=0.0))
    return any(d.id == doc_id for d in res.docs)


async def staleness():
    name = f"test-stale-{RUN.lower()}"
    reader, writer = MossClient(PID, KEY), MossClient(PID, KEY)
    await writer.create_index(name, [DocumentInfo(id="refund", text="Refunds are issued within 5 business days.")])
    new_doc = DocumentInfo(id="zebra", text="The zebra stripe discount gives 40 percent off for nonprofits.")

    await reader.load_index(name)  # default: auto_refresh=False
    await writer.add_docs(name, [new_doc])
    t0 = time.perf_counter()
    for total in (0, 10, 30):
        await asyncio.sleep(max(0.0, total - (time.perf_counter() - t0)))
        log("default_load_after_update", waited_s=round(time.perf_counter() - t0), sees_new_doc=await has_doc(reader, name, "zebra"))
    await reader.load_index(name)
    log("after_reload", sees_new_doc=await has_doc(reader, name, "zebra"))

    await writer.delete_docs(name, ["zebra"])
    await reader.load_index(name, auto_refresh=True, polling_interval_in_seconds=5)
    await writer.add_docs(name, [new_doc])
    t0 = time.perf_counter()
    visible = False
    while not visible and time.perf_counter() - t0 < 60:
        visible = await has_doc(reader, name, "zebra")
        if not visible:
            await asyncio.sleep(1)
    log("auto_refresh_5s", visible=visible, seconds=round(time.perf_counter() - t0, 1))
    await reader.close()
    await writer.delete_index(name)


async def size():
    writer = MossClient(PID, KEY)
    for n in (1_000, 10_000):
        name = f"test-size-{n}-{RUN.lower()}"
        await writer.create_index(name, [DocumentInfo(id=f"d{i}", text=f"Document {i} about billing, refunds and invoices, topic {i % 97}.")
                                         for i in range(n)])
        cache = f"/tmp/moss-size-{RUN}-{n}"
        reader = MossClient(PID, KEY, cache_path=cache)
        t0 = time.perf_counter()
        await reader.load_index(name)
        load_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        await reader.query(name, "refund for topic 3", QueryOptions(top_k=5))
        query_ms = (time.perf_counter() - t0) * 1000
        disk_mb = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(cache) for f in fs) / 1e6
        log("size", docs=n, load_s=round(load_s, 2), first_query_ms=round(query_ms, 1), index_on_disk_mb=round(disk_mb, 2))
        await reader.close()
        shutil.rmtree(cache, ignore_errors=True)
        await writer.delete_index(name)


async def main():
    await staleness()
    await size()
    os.makedirs("logs", exist_ok=True)
    path = f"logs/search_sdk_{RUN}.json"
    json.dump(LOG, open(path, "w"), indent=2)
    print("log:", path)


asyncio.run(main())
