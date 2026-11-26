# Moss Inference work sample

The one-pager is `report.md`. This folder has the code I ran and the logs it produced.

## Setup
```
pip install -r requirements.txt
cp .env.example .env   # add MOSS_PROJECT_ID and MOSS_PROJECT_KEY
```
Run scripts from this folder. Logs go to `logs/`.

## Scripts
| Script | What it checks | Log |
|---|---|---|
| `scripts/search_sdk.py` | A loaded index stays stale after a cloud update until reload or auto-refresh; load time and size vs doc count | `logs/search_sdk_*.json` |
| `scripts/inference.py` | Latency per model, retrieval overhead, RAG answers, OpenAI compatibility, errors | `logs/inference_*/` (`summary.md` has the tables) |
| `scripts/run_task.py` | Runs one Task, saves task, trace and files, compares with the expected answer | `logs/tasks/<task_id>/` |
| `scripts/glm_final_step.py` | Replays the step where GLM Tasks failed, through the Inference API | `logs/glm_final_step_*.json` |

`logs/tasks/task_ae174453...` is the Task I started from the portal. I downloaded it with the API, so it has no `request.json` or `summary.json`.

## Tasks
`tasks/*.json` are the requests and `tasks/*.expected.json` the correct answers, taken from the websites.
```
python scripts/run_task.py tasks/02_india_oscar_song.json --label balanced
python scripts/run_task.py tasks/02_india_oscar_song.json --model z-ai/glm-5.3 --no-schema --effort medium --max-cost 0.10 --label portal-like
python scripts/run_task.py tasks/01_books_travel.json --no-start-url --label no-url
```

## Portal
`portal/screenshots/` has the two Playground runs from the report.
