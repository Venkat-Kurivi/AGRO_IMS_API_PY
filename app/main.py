from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.inventory import router as inventory_router
from app.application.authentication import password_hash
from app.core.config import settings
from app.domain.exceptions import ConflictError, NotFoundError, RuleViolation
from app.infrastructure.database import SessionLocal, UserRecord, initialize_database
from app.infrastructure.relational_inventory_repository import SqlAlchemyInventoryRepository


@asynccontextmanager
async def lifespan(_application: FastAPI):
    del _application
    initialize_database()
    with SessionLocal() as session:
        if session.query(UserRecord).count() == 0:
            session.add(UserRecord(
                id="us1",
                name="AGRO Administrator",
                username=settings.initial_admin_username,
                password_hash=password_hash.hash(settings.initial_admin_password),
                role="Admin",
                active=True,
            ))
            session.commit()
        repository = SqlAlchemyInventoryRepository(session)
        if not repository.list("branches"):
            for branch in [
                {"id": "br1", "name": "Karimnagar Main", "code": "KRM", "city": "Karimnagar", "phone": "0878 224 1100"},
                {"id": "br2", "name": "Warangal Depot", "code": "WGL", "city": "Warangal", "phone": "0870 245 7781"},
                {"id": "br3", "name": "Nizamabad Yard", "code": "NZB", "city": "Nizamabad", "phone": "08462 233 909"},
            ]:
                repository.save("branches", branch)
            session.commit()
    yield


app = FastAPI(title="AGRO Inventory Management API", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(inventory_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFoundError)
def not_found_handler(_request: Request, error: NotFoundError) -> JSONResponse:
    del _request
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(ConflictError)
def conflict_handler(_request: Request, error: ConflictError) -> JSONResponse:
    del _request
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(RuleViolation)
def rule_violation_handler(_request: Request, error: RuleViolation) -> JSONResponse:
    del _request
    return JSONResponse(status_code=400, content={"detail": str(error)})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}