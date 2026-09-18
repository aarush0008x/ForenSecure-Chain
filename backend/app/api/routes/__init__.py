from app.api.routes.erasure import router as erasure_router
from app.api.routes.files import router as files_router
from app.api.routes.recovery import router as recovery_router
from app.api.routes.verification import router as verification_router
from app.api.routes.blockchain import router as blockchain_router
from app.api.routes.audit import router as audit_router
from app.api.routes.reports import router as reports_router

__all__ = [
	"audit_router",
	"blockchain_router",
	"erasure_router",
	"files_router",
	"recovery_router",
	"reports_router",
	"verification_router",
]
