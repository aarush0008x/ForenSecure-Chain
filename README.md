# ForenSecure Chain

Backend-first prototype for SIH 2026 problem statement SIH26149.

The backend exposes the file, erasure, recovery, verification, audit, blockchain, and report APIs for a separately developed frontend. See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for endpoint contracts, local CORS configuration, setup, and testing.

See [docs/backend-architecture.md](docs/backend-architecture.md) for the planned design.

## Run the complete demo

The project keeps the vanilla HTML/CSS/JavaScript frontend separate from the FastAPI backend. You need Python installed. MySQL is required for the normal backend configuration; the automated tests can use SQLite instead.

### 1. Configure the backend

From the repository root, create and activate a virtual environment, install dependencies, and copy the environment template:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with the MySQL username, password, database name, and a writable `STORAGE_DIR`. Create the database in MySQL before initializing tables:

```sql
CREATE DATABASE forensecure_chain CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Start MySQL using your local installation or service manager, then initialize the tables and start FastAPI:

```powershell
Set-Location backend
python -m scripts.init_db
uvicorn app.main:app --reload
```

Keep that terminal running. The backend is available at `http://127.0.0.1:8000`.

### 2. Start the frontend

Open a second terminal at the repository root and serve the static frontend:

```powershell
python -m http.server 5173 --directory frontend
```

Open `http://127.0.0.1:5173` in a browser. The frontend calls the documented API at `http://127.0.0.1:8000` through [frontend/js/api.js](frontend/js/api.js). The backend already permits this origin through `CORS_ORIGINS`.

### 3. Basic demonstration flow

1. Open **Evidence files** and upload a real evidence file. The backend returns its file ID and SHA-256 hash.
2. Select the file and open **Secure erasure** to review the hash and confirm the destructive operation.
3. Use **File recovery** to upload a controlled sample binary. The frontend then sends the returned file ID to the real recovery scan endpoint.
4. Open **Verification** and run a hash comparison for the selected file.
5. Inspect **Audit ledger** for the actual chained blocks and use **Verify chain** to recalculate their links.
6. Inspect **Audit trail** for operation events and **Reports** to generate and download the backend JSON report.

The frontend shows loading, empty, offline, error, confirmation, and success states from actual API results. It does not fabricate evidence records or operation results.

For the endpoint contract and manual API examples, see [API_DOCUMENTATION.md](API_DOCUMENTATION.md). For backend tests:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest -q backend/tests
```
