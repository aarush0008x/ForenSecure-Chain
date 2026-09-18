from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.files import router as files_router
from app.api.routes.erasure import router as erasure_router
from app.api.routes.recovery import router as recovery_router
from app.api.routes.verification import router as verification_router
from app.api.routes.blockchain import router as blockchain_router
from app.api.routes.audit import router as audit_router
from app.api.routes.reports import router as reports_router
from app.core.config import get_settings


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.add_middleware(
	CORSMiddleware,
	allow_origins=settings.cors_allowed_origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)
app.include_router(files_router)
app.include_router(erasure_router)
app.include_router(recovery_router)
app.include_router(verification_router)
app.include_router(blockchain_router)
app.include_router(audit_router)
app.include_router(reports_router)