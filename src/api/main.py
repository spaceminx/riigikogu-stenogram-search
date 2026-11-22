import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import router
from src.api.search import LemmatizerUnavailableError
from src.load.loader import create_tables

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        applied = create_tables()
        if applied:
            logger.info("Applied migrations: %s", ", ".join(applied))
        else:
            logger.info("Schema up to date")
    except Exception as e:
        logger.warning("Database schema check on startup encountered an issue: %s", e)
    yield


app = FastAPI(title="Riigikogu Stenogram Search API", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    # jsonable_encoder: custom validators put the raised exception into the error's ctx
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(LemmatizerUnavailableError)
async def lemmatizer_unavailable_handler(request: Request, exc: LemmatizerUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"detail": "Otsingu keeletöötlus pole hetkel saadaval."},
    )


allowed_origins = [
    origin.strip() for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
