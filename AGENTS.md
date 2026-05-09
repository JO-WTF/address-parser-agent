# AGENTS.md

## Project overview

This repository contains an Excel address-parsing Agent system. The app lets a user upload an Excel file, asks an LLM to infer which column contains address text, lets the user confirm that column, then processes rows one by one with the LLM to extract structured contact/address fields. Progress is shown live in the frontend, and the processed Excel file can be downloaded when the task completes.

Think of the backend core as a web version of this pandas/LLM script:

```python
df = pd.read_excel(input_excel).fillna("")
address_col = llm_guess_address_column(df.columns.tolist())
copy_excel(input_excel, output_excel)
for row_number, row in enumerate(df.itertuples(index=False), start=1):
    text = getattr(row, address_col, "")
    result = llm_extract_info(text)
    write_result_to_excel(output_excel, row_number + 1, result)
```

## Repository layout

- `project/backend/` - Python backend using FastAPI, pandas/openpyxl, SQLite, and the OpenAI Python SDK.
- `project/frontend/` - Vue 3 frontend using Element Plus, axios, Vite, and browser WebSocket APIs.
- `project/README.md` - Startup instructions, example prompts, API list, and LLM configuration notes.

## Backend architecture

### Entry point

- `project/backend/main.py` creates the FastAPI application.
- It registers routers from:
  - `api/upload.py`
  - `api/agent.py`
  - `api/task.py`
- It enables permissive CORS for frontend/backend development.
- On startup, it initializes the SQLite database.
- It also defines the WebSocket endpoint `/ws/task/{task_id}`.

### API modules

- `project/backend/api/upload.py`
  - `POST /upload`
  - Accepts `.xlsx` and `.xls` files only.
  - Saves uploads under `project/backend/uploads/`.
  - Creates output paths under `project/backend/outputs/`.
  - Creates a `Task` row with status `uploaded`.

- `project/backend/api/agent.py`
  - `POST /analyze`
  - Receives Excel headers and calls `Agent.analyze_headers()`.
  - Returns the guessed `address_field`.

- `project/backend/api/task.py`
  - `GET /headers/{task_id}` reads Excel headers.
  - `POST /run` starts or resumes processing.
  - `GET /tasks` lists historical tasks.
  - `POST /task/{task_id}/stop` cancels a running job.
  - `DELETE /task/{task_id}` deletes the task and associated files.
  - `GET /task/{task_id}` returns one task's current state.
  - `GET /download/{task_id}` downloads the result workbook.
  - `publish()` sends progress events to WebSocket subscribers and stores recent events in memory.

### Task lifecycle

Typical task statuses:

- `uploaded` - file has been uploaded and task metadata exists.
- `running` - background processing has started.
- `completed` - all rows were processed successfully.
- `failed` - processing raised an exception.
- `stopped` - processing was cancelled by the user.

Important task fields are defined in `project/backend/task/model.py`:

- `id`
- `status`
- `progress`
- `current_row`
- `total_rows`
- `file_path`
- `output_path`
- `selected_column`
- extracted fields such as `contact_name`, `contact_phone`, `contact_email`, `company_name`, `address_detail`, `province`, `city`, `country`, `postcode`, `delivery_note`
- `error`
- timestamps

`project/backend/task/manager.py` is the persistence layer around SQLite. It creates, lists, reads, updates, and deletes tasks.

### Database

- SQLite database path: `project/backend/tasks.db`.
- Schema setup lives in `project/backend/storage/db.py`.
- The main table is `tasks`.
- The database stores task progress and the most recent extracted fields, not every row's complete parsed output. Row-level output is written to the Excel result file.

### Excel handling

`project/backend/tools/excel.py` uses:

- pandas for reading headers and data.
- openpyxl for copying/writing workbook output.

Current output workbook behavior:

- The original workbook is copied to the output path.
- `write_result_row()` appends and writes only these columns:
  - `name`
  - `phone`
  - `address`
  - `province`
  - `city`

Note: `Agent.extract_info()` returns more fields than are currently written to the workbook, including `email`, `company_name`, `country`, `postcode`, and `remark`. If the desired downloaded Excel should include those fields, update `ExcelTool.write_result_row()` accordingly.

### LLM agent

`project/backend/agent/core.py` wraps the OpenAI Python SDK.

- Configuration is read from `project/backend/config.ini` under the `[llm]` section.
- Expected keys:
  - `base_url`
  - `api_key`
  - `model`
- Defaults target an OpenAI-compatible local server at `http://localhost:11434/v1` with model `qwen2.5:7b`.

Prompt templates are in `project/backend/agent/prompt.py`:

- `HEADER_PROMPT` asks the model to infer only the detailed address field from Excel headers.
- `EXTRACT_PROMPT` asks the model to extract structured fields from one text string and return JSON only.

The LLM output parser first tries direct `json.loads()`, then falls back to extracting the substring between the first `{` and the last `}`.

## Asyncio and WebSocket notes

This project uses asyncio mostly to keep the FastAPI app responsive while long-running work happens in the background.

- `async def` endpoints can `await` other async operations.
- `asyncio.create_task(process_task(task_id))` starts the row-processing job in the background so `POST /run` can return quickly.
- `asyncio.to_thread(...)` is used for blocking synchronous work such as pandas/openpyxl operations and synchronous LLM calls.
- `await asyncio.sleep(0)` inside the row loop yields control back to the event loop.
- `asyncio.Task.cancel()` is used to stop a running job.

WebSocket flow:

- Frontend connects to `/ws/task/{task_id}`.
- Backend stores the connection in `subscribers[task_id]`.
- `publish(task_id, payload)` is the backend's broadcast helper for task progress events. It first appends the payload to `event_buffers[task_id]`, trims the buffer to the latest 200 events, then sends the same JSON payload to every currently connected WebSocket in `subscribers[task_id]`. If sending fails for a connection, that dead connection is removed from the subscriber set.
- `event_buffers[task_id]` is an in-memory replay buffer, not a database table. It exists so that if the browser connects after a task has already started, reconnects after a network hiccup, or switches back to a running historical task, the WebSocket endpoint can immediately send recently buffered progress events before waiting for new events.
- The buffer is best-effort and process-local: it disappears when the backend process restarts, and only the latest 200 events are retained. Durable progress still comes from the `tasks` SQLite row (`status`, `current_row`, `total_rows`, `progress`), while row-level WebSocket log events are only buffered in memory.
- Frontend falls back to polling task status if the WebSocket connection is unavailable or closes before the task reaches a terminal status.

## Frontend architecture

- `project/frontend/src/main.js` mounts the Vue app and installs Element Plus.
- `project/frontend/src/App.vue` contains the main page UI and most frontend logic.
- `project/frontend/src/api/client.js` creates an axios client.
- `project/frontend/config.js` defines default backend HTTP and WebSocket base URLs.
- `project/frontend/vite.config.js` configures the Vite dev server on `0.0.0.0:8099`.

Important frontend behaviors in `App.vue`:

- Upload Excel.
- Fetch headers.
- Call `/analyze` to guess the address field.
- Let the user confirm or edit the field.
- Connect to WebSocket before starting a run.
- Call `/run` to start or resume processing.
- Display progress, logs, status, and parsed row output.
- Stop, delete, list, select, and download tasks.

## Main end-to-end flow

1. User uploads Excel in the frontend.
2. Frontend sends `POST /upload`.
3. Backend saves the file and creates a task.
4. Frontend calls `GET /headers/{task_id}`.
5. Backend reads headers with pandas.
6. Frontend calls `POST /analyze` with the headers.
7. Backend asks the LLM to return `address_field`.
8. User confirms or edits the field.
9. Frontend opens WebSocket `/ws/task/{task_id}`.
10. Frontend calls `POST /run` with `task_id` and `address_field`.
11. Backend creates a background asyncio task.
12. Backend reads the Excel rows, calls the LLM for each selected-column value, writes results to the output workbook, updates SQLite, and publishes progress events.
13. Frontend updates progress/logs from WebSocket events or polling fallback.
14. When status is `completed`, the frontend enables result download.
15. User downloads the result from `GET /download/{task_id}`.

## Development commands

Backend:

```bash
cd project/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd project/frontend
npm install
npm run dev
```

Backend syntax check:

```bash
python -m compileall project/backend
```

## Coding notes for future agents

- Do not wrap imports in try/except blocks.
- Prefer `rg` over recursive grep-style commands for repository searches.
- Avoid committing generated folders such as `project/frontend/node_modules/`.
- When creating pull requests, target the original/upstream repository rather than a fork; verify the base repository before submitting.
- If changing backend task processing, check resume/stop behavior carefully.
- If adding new extracted fields, update both backend Excel writing and frontend display/download expectations.
- If changing WebSocket payload shape, update both `publish()` consumers and `App.vue` handling.
- If making user-visible frontend changes, run the frontend if practical and capture a screenshot.
