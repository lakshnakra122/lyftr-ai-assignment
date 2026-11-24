# Run in VS Code — Simple Steps

You need only 3 things installed first:
1. **VS Code**
2. **Python 3.11+** — check: open a terminal and type `python --version`
3. **Node.js 18+** — check: `node --version`

No real API key is needed to run and test. Dummy keys are already set in the
VS Code tasks. Real keys can be added later for deployment.

---

## Step 1 — Open the project
1. Unzip `Lyftr_AI_FullStack_Assignment_LakshNakra.zip`
2. VS Code → **File → Open Folder** → select the `lyftr-ai-assignment` folder
3. If VS Code asks "Do you trust the authors?" → click **Yes, I trust**
4. If VS Code suggests extensions (bottom-right popup) → click **Install All**

## Step 2 — Install (only first time)
Press **Ctrl + Shift + P** (Mac: Cmd + Shift + P), type **Tasks: Run Task**, press Enter.

1. Run task **"1. Backend: install"** — wait till it finishes (1–2 minutes)
2. Run task **"2. Frontend: install"** — wait till it finishes (1–2 minutes)

## Step 3 — Run the app (2 terminals, both stay open)
Again **Tasks: Run Task**:

1. Run task **"3. Run Backend (8000)"** — a terminal opens, keep it running.
   You should see: `Uvicorn running on http://127.0.0.1:8000`
2. Run task **"4. Run Frontend (3000)"** — a second terminal opens, keep it running.

## Step 4 — Open and test
Open in your browser:
- **App:** http://localhost:3000
- **Backend health:** http://localhost:8000/health → `{"status":"ok","keys_configured":2,"cache_enabled":true}`

Try in the app:
1. Type `What is the capital of France?` → Send → reply "Paris", source **LIVE_INFERENCE**
2. Press **F5 / reload the page** (new session starts), send the **same** message again → source **LLM_CACHE**, reply same, latency much less
3. Type `Hi, my name is Laksh` → Send. Then type `What is my name?` → it replies with your name (multi-turn memory works)

## Step 5 — Run the tests (optional, for confidence)
**Tasks: Run Task → "Run Tests"** → you should see **10 passed**.

## Stop the app
In each running terminal, press **Ctrl + C**.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| `python is not recognized` | Install Python from python.org and tick **"Add Python to PATH"** during install, then restart VS Code |
| `node is not recognized` | Install Node.js LTS from nodejs.org, then restart VS Code |
| Port 8000 / 3000 already in use | Close the old terminal running the app (Ctrl + C), then run the task again |
| Frontend opens but chat says "Could not reach the server" | Backend terminal is not running — run task 3 first, then refresh the page |
| Backend terminal shows a red error | Copy the full error and send it to Muse in chat — do not change code yourself |

## Manual way (without VS Code tasks)

Backend — VS Code terminal 1:
```powershell
# Windows PowerShell
cd backend
pip install -r requirements.txt
$env:LLM_API_KEYS="sk-dummy-key-1,sk-dummy-key-2"; $env:DATABASE_URL="sqlite:///./app.db"; $env:ENABLE_FAILURE_SIMULATION="true"; uvicorn app.main:app --port 8000
```
```bash
# Mac / Linux
cd backend
pip install -r requirements.txt
LLM_API_KEYS=sk-dummy-key-1,sk-dummy-key-2 DATABASE_URL=sqlite:///./app.db ENABLE_FAILURE_SIMULATION=true uvicorn app.main:app --port 8000
```

Frontend — VS Code terminal 2 (Terminal → New Terminal):
```bash
cd frontend
npm install
npm run dev
# open http://localhost:3000  (Vite uses the backend at http://localhost:8000 by default in this project)
```
