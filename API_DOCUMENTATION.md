# ForenSecure Chain API

Base URL: `http://127.0.0.1:8000`

The API is JSON-based except for file upload and report download. Timestamps are ISO-8601 strings. Errors use FastAPI's standard shape:

```json
{"detail": "File not found"}
```

CORS is enabled for `localhost` and `127.0.0.1` on ports `3000` and `5173` by default. Set `CORS_ORIGINS` to a comma-separated list for another frontend origin.

## Endpoints

### Files

#### `POST /api/files/upload`

Uploads a controlled file, calculates SHA-256, stores it below `STORAGE_DIR/uploads`, and records the file, audit events, and blockchain blocks.

Request: `multipart/form-data` with required field `upload` (the file).

Response `201`:

```json
{
  "file_id": "9b1deb4d-3b7d-4bad-9bdd-2b1c5e7e4d20",
  "original_filename": "evidence.bin",
  "file_path": "uploads/9b1deb4d-3b7d-4bad-9bdd-2b1c5e7e4d20.bin",
  "file_size": 17,
  "file_type": "application/octet-stream",
  "original_hash": "sha256-hex-64-character-value",
  "upload_timestamp": "2026-09-19T12:00:00Z",
  "status": "uploaded"
}
```

Errors: `400` for missing/invalid filename, empty file, size limit, storage, or database failure; `422` for invalid multipart input.

#### `GET /api/files`

Request: no parameters.

Response `200`:

```json
{"items": [{"file_id": "...", "original_filename": "evidence.bin", "file_path": "uploads/...bin", "file_size": 17, "file_type": "application/octet-stream", "original_hash": "...", "upload_timestamp": "2026-09-19T12:00:00Z", "status": "uploaded"}], "total": 1}
```

Errors: `500` for database failure.

#### `GET /api/files/{file_id}`

Path parameter: `file_id` (string UUID or registered file identifier).

Response `200`: the same file object returned by upload.

Errors: `404` if the file does not exist; `500` for database failure.

### Secure erasure

#### `POST /api/erasure/{file_id}`

Path parameter: `file_id`. Request body: none. Verifies the stored SHA-256, overwrites the controlled file with zeroes, deletes it, and records the operation, certificate, audit event, and blockchain block.

Response `200`:

```json
{"certificate_id": "...", "file_id": "...", "original_hash": "...", "method": "overwrite_then_delete", "timestamp": "2026-09-19T12:05:00Z", "status": "completed"}
```

Errors: `400` for integrity, storage, path, or persistence failures; `404` if the file is missing; `409` if already erased.

#### `GET /api/erasure/{file_id}/certificate`

Path parameter: `file_id`. Request: none.

Response `200`: the erasure certificate object above.

Errors: `400` for an invalid request; `404` if the file or certificate does not exist.

### Recovery

#### `POST /api/recovery/scan`

Scans a previously uploaded controlled source for supported JPEG, PNG, and PDF signatures, carves artifacts, extracts available metadata, hashes artifacts, and records recovery, audit, and blockchain data.

Request JSON:

```json
{"file_id": "..."}
```

Response `201`:

```json
{
  "recovery_id": "...",
  "file_id": "...",
  "number_of_files_detected": 1,
  "recovery_timestamp": "2026-09-19T12:10:00Z",
  "recovered_files": [{
    "recovery_id": "...",
    "recovered_filename": "recovered_0001.jpg",
    "file_type": "image/jpeg",
    "file_size": 1234,
    "recovered_path": "recovered/.../recovered_0001.jpg",
    "recovered_hash": "...",
    "recovery_timestamp": "2026-09-19T12:10:00Z",
    "metadata_info": {"artifact": {}, "actual": {}, "inferred": {}, "source_filesystem": {}}
  }]
}
```

Errors: `400` for path, integrity, size, carving, storage, or persistence failures; `404` if the source file is not registered; `422` for invalid JSON.

#### `GET /api/recovery/results/{recovery_id}`

Path parameter: `recovery_id`.

Response `200`: the recovery object above.

Errors: `404` if the recovery scan does not exist; `500` for database failure.

### Verification

#### `GET /api/verification/{file_id}`

Path parameter: `file_id`. Request: none. Compares the registered source hash with the current controlled file and verifies hashes for recovered artifacts. The request itself records an operation, audit event, and blockchain block.

Response `200`:

```json
{
  "file_id": "...",
  "hash_algorithm": "SHA-256",
  "original_hash": "...",
  "current_hash": "...",
  "recovered_hashes": [{"recovery_id": "...", "recovered_filename": "recovered_0001.jpg", "stored_hash": "...", "current_hash": "...", "status": "VERIFIED"}],
  "comparison_result": "VERIFIED",
  "verification_timestamp": "2026-09-19T12:15:00Z",
  "related_operation": {"operation_id": "...", "operation_type": "verification", "status": "completed", "started_at": "...", "completed_at": "..."},
  "related_blockchain_block": {"block_id": 4, "block_index": 4, "action": "verification", "timestamp": "...", "previous_hash": "...", "current_hash": "..."},
  "details": {"hash_algorithm": "SHA-256", "comparison_result": "VERIFIED"}
}
```

`comparison_result` and recovered status can be `VERIFIED`, `MISMATCH`, or `NOT_AVAILABLE`. Errors: `400` for recording failure; `404` if the file does not exist.

### Audit and blockchain

#### `GET /api/audit/{file_id}`

Path parameter: `file_id`.

Response `200`:

```json
{"file_id": "...", "total_events": 2, "events": [{"audit_id": "...", "action": "upload", "timestamp": "...", "file_id": "...", "hash": "...", "operation_id": null, "blockchain_block_index": 0, "details": {}, "status": "recorded"}]}
```

Errors: `404` if the file does not exist; `500` for database failure.

#### `GET /api/blockchain`

Request: none.

Response `200`:

```json
{"total_blocks": 1, "blocks": [{"block_id": 1, "block_index": 0, "timestamp": "...", "action": "upload", "file_id": "...", "file_hash": "...", "previous_hash": null, "current_hash": "...", "audit_data": {}}]}
```

Errors: `500` for database failure.

#### `GET /api/blockchain/verify`

Request: none. Recalculates every block hash and link.

Response `200`:

```json
{"valid": true, "total_blocks": 1, "invalid_blocks": []}
```

Errors: `500` for database failure.

#### `GET /api/blockchain/file/{file_id}`

Path parameter: `file_id`.

Response `200`:

```json
{"file_id": "...", "total_blocks": 1, "blocks": [{"block_id": 1, "block_index": 0, "timestamp": "...", "action": "upload", "file_id": "...", "file_hash": "...", "previous_hash": null, "current_hash": "...", "audit_data": {}}]}
```

Errors: `500` for database failure. An unknown file identifier returns an empty block list.

### Reports

#### `GET /api/reports/{file_id}`

Path parameter: `file_id`. Request: none. Generates and stores a JSON report when erasure or recovery evidence exists, and records report generation in the audit and blockchain records.

Response `200`:

```json
{"file_id": "...", "generated_at": "...", "report_path": "reports/....json", "download_url": "/api/reports/.../download", "erasure_certificate": null, "recovery_reports": [], "verification_information": null, "blockchain_audit_references": []}
```

Errors: `400` if no erasure/recovery evidence or report generation fails; `404` if the file does not exist.

#### `GET /api/reports/{file_id}/download`

Path parameter: `file_id`. Request: none.

Response `200`: downloadable `application/json` containing the report JSON above, with a `{file_id}-report.json` filename.

Errors: `404` if no stored report exists, its path is outside controlled storage, or its file is unavailable.

## Repository status

### Fully working

- FastAPI route registration and Pydantic response validation.
- Upload, SHA-256 hashing, controlled storage, database persistence, audit, and blockchain recording.
- Prototype secure erasure with certificate generation.
- Signature carving for JPEG, PNG, and PDF samples, recovered-file hashing, metadata, persistence, audit, and blockchain recording.
- Source and recovered-file verification.
- Audit trail, blockchain listing/verification, report generation, and report download.
- Local CORS middleware for separately hosted development frontends.
- Automated backend suite: `13 passed` at the time of documentation.

### Prototype or mock functionality

- The blockchain is a local tamper-evident SQL table, not a distributed blockchain network.
- Erasure uses a single zero overwrite followed by deletion; it is a prototype sanitization method, not a certified hardware or multi-pass sanitization standard.
- Recovery is signature carving for three formats, not a complete forensic filesystem or disk recovery engine.
- Metadata is limited to available filesystem facts and recognized file-header metadata.
- Authentication, authorization, rate limiting, production object storage, and background job processing are not implemented.

### Additional configuration required

1. Copy `.env.example` to `.env`.
2. Create the MySQL database named by `DB_NAME`.
3. Set `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and optionally `DATABASE_URL`.
4. Set `STORAGE_DIR` to a writable controlled directory.
5. Set `CORS_ORIGINS` to the exact frontend origins used in development.
6. For production, add authentication, HTTPS, migrations, backups, and a production storage/sanitization policy.

## Run locally

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with MySQL and storage settings.
Set-Location backend
python -m scripts.init_db
uvicorn app.main:app --reload
```

The API is then available at `http://127.0.0.1:8000`. FastAPI's interactive documentation is at `/docs`, and the OpenAPI schema is at `/openapi.json`.

## Test every API

Run the automated suite from the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest -q backend/tests
```

The tests use an isolated SQLite database and temporary controlled storage, so they do not require MySQL. For manual endpoint testing, start the server and execute the endpoints in this order: upload and list/get; erasure and certificate; recovery scan and results; verification; audit; blockchain list, verify, and file; report and report download. Use the examples above or import `/openapi.json` into an API client.
