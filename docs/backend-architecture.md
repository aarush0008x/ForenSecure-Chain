# Backend Architecture

## Scope

ForenSecure Chain is a FastAPI backend prototype for secure data erasure, file recovery/file carving, metadata reconstruction, SHA-256 integrity verification, and tamper-evident audit records.

The backend owns the workflow and exposes REST APIs. A separate frontend will consume those APIs later.

## Core Workflow

```text
Input file
  -> SHA-256 pre-operation hash
  -> Erase or recover operation
  -> SHA-256 post-operation hash / recovered artifact hash
  -> verification result
  -> audit event
  -> chained audit record
  -> certificate or report
```

Every operation should produce a stable operation identifier and an audit record. The audit record links to the previous record through a hash so that later changes are detectable. This is blockchain-style tamper evidence for the prototype, not a distributed blockchain network.

## Package Responsibilities

- `backend/app/api`: HTTP routing and request/response orchestration only.
- `backend/app/core`: application settings, dependency wiring, and shared error/security primitives.
- `backend/app/db`: MySQL session management and persistence models.
- `backend/app/schemas`: Pydantic contracts exposed by the REST API.
- `backend/app/services`: use-case orchestration for erase, recovery, metadata, reports, and audit workflows.
- `backend/app/integrity`: SHA-256 hashing and verification primitives.
- `backend/app/storage`: controlled input, recovered-artifact, and report storage boundaries.
- `backend/app/audit`: append-only audit chain construction and validation.
- `backend/tests`: unit and API tests grouped by behavior.

## Planned Resource Areas

- `POST /api/files/upload`: validate, store, hash, and audit an uploaded file.
- `GET /api/files`: list registered files.
- `GET /api/files/{file_id}`: retrieve one registered file.
- `POST /api/erasure/{file_id}`: overwrite and delete a controlled file.
- `GET /api/erasure/{file_id}/certificate`: retrieve the erasure certificate.
- `POST /api/recovery/scan`: scan a registered controlled sample for JPG, PNG, and PDF signatures.
- `GET /api/recovery/results/{recovery_id}`: retrieve a recovery scan and its recovered artifacts.
- `GET /api/verification/{file_id}`: compare stored and current SHA-256 values and record verification.
- `GET /api/blockchain`: list the local tamper-evident ledger.
- `GET /api/blockchain/verify`: verify block ordering, links, and recalculated hashes.
- `GET /api/blockchain/file/{file_id}`: list ledger records for one file.
- `GET /api/audit/{file_id}`: return the chronological audit timeline for one file.
- `GET /api/reports/{file_id}`: generate an erasure/recovery report and record report generation.
- `GET /api/reports/{file_id}/download`: download the generated JSON report.
- `POST /api/v1/files/hash`: calculate and register a file hash.
- `POST /api/v1/erase`: execute a configured sanitization operation.
- `POST /api/v1/recovery`: run recovery/file-carving workflow against an input artifact.
- `GET /api/v1/operations/{operation_id}`: retrieve operation status and results.
- `POST /api/v1/verify`: verify artifact integrity against a recorded hash.
- `GET /api/v1/audit/{operation_id}`: retrieve the operation audit trail.
- `GET /api/v1/audit/chain/verify`: validate the audit chain.
- `GET /api/v1/reports/{operation_id}`: produce or retrieve a certificate/report.

The exact request and response schemas will be defined alongside each implementation increment.

The upload module stores files below the configured `STORAGE_DIR` in an `uploads` subdirectory. Stored filenames use the generated `file_id` and retain only the lowercase extension; the original filename remains database metadata. Each successful upload creates an `audit_logs` row and a chained `blockchain_blocks` row in the same database transaction.

Recovery scans accept the `file_id` of a file already registered through the controlled upload endpoint. They read that source without modifying it and write carved artifacts below `STORAGE_DIR/recovered/{recovery_id}`. `recovery_runs` stores one scan result, while `recovered_files` stores one row per carved artifact. Metadata under `actual` comes from recognized file bytes; metadata under `inferred` describes carving boundaries and reconstructed context.

The blockchain-style ledger is local database state for prototype demonstration. It is not a Hyperledger Fabric network or a production blockchain. Existing upload, erasure, recovery, and verification workflows append chained blocks. Future report generation should use `app.blockchain.ledger.append_block()` with action `report_generation`.

## Persistence Model Direction

The initial MySQL model should keep these concepts separate:

- `files`: source/recovered artifact identity and metadata.
- `operations`: erase or recovery lifecycle and status.
- `integrity_records`: SHA-256 values and verification outcomes.
- `audit_events`: operation events, actor/context data, previous hash, and record hash.
- `reports`: generated certificate/report metadata and artifact location.

Database access should remain behind repositories or service boundaries so hashing, recovery, and audit logic can be tested without MySQL.

## Implementation Order

1. Application settings, FastAPI entry point, and health check.
2. Pydantic contracts and MySQL session foundation.
3. SHA-256 hashing and integrity verification service.
4. Operation records and secure erasure service.
5. Recovery/file-carving service with metadata reconstruction.
6. Append-only audit chain and chain verification.
7. Certificate/report generation and end-to-end API tests.

## Local Database Initialization

For the prototype, `backend/app/db/init_db.py` uses SQLAlchemy `create_all()` after importing all models. Run it from the repository root with:

```text
python -m pip install -r requirements.txt
cd backend
python -m scripts.init_db
```

This is intentionally suitable for a local demo and does not alter existing tables. Once the schema stabilizes, Alembic revisions should replace `create_all()` for repeatable upgrades.
