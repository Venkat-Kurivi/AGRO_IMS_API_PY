from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.auth import router as auth_router
from app.api.inventory import router as inventory_router
from app.domain.exceptions import ConflictError, NotFoundError, RuleViolation
from app.infrastructure.database import initialize_database


@asynccontextmanager
async def lifespan(_application: FastAPI):
    del _application
    initialize_database()
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


@app.exception_handler(IntegrityError)
def integrity_error_handler(_request: Request, error: IntegrityError) -> JSONResponse:
    del _request, error
    return JSONResponse(status_code=409, content={"detail": "The change conflicts with existing data."})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}