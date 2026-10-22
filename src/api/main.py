import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

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
    if request.url.path.startswith("/rss/"):
        # Return plain text error for RSS routes
        errors = exc.errors()
        msg = "Vigane päring."
        if errors:
            first_err = errors[0]
            err_type = first_err.get("type", "")
            field = first_err.get("loc", [""])[-1]
            if err_type == "missing":
                msg = f"Puuduv väli: {field}."
            elif field == "q":
                msg = "Otsingupäring ei tohi olla tühi."
            elif "pattern" in err_type:
                msg = f"Vigane väärtus: {field}."
            elif "msg" in first_err:
                msg = first_err["msg"]
        return PlainTextResponse(content=msg, status_code=422)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/rss/"):
        return PlainTextResponse(content=str(exc.detail), status_code=exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(LemmatizerUnavailableError)
async def lemmatizer_unavailable_handler(request: Request, exc: LemmatizerUnavailableError):
    if request.url.path.startswith("/rss/"):
        return PlainTextResponse(
            content="Otsingu keeletöötlus pole hetkel saadaval.", status_code=503
        )
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
    expose_headers=[
        "Content-Disposition",
        "X-Total-Count",
        "X-Export-Count",
        "X-Export-Truncated",
    ],
)
app.include_router(router)
