from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse  # type: ignore
from pygelf import GelfTcpHandler
from .routers import (
    gs,
    hello,
    request,
    ground_station,
    auth,
    satellite,
    exclusion_cone,
    user,
    schedule,   # Added by MD
    metrics,    # Added by MD
)

import logging

logger = logging.getLogger(__name__)

# for debugging, elevate the log level of the sqlalchemy engine
db_logger = logging.getLogger("sqlalchemy.engine")
db_logger.setLevel(logging.DEBUG)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gs.router, prefix="/api/v1")
app.include_router(hello.router, prefix="/api/v1")
app.include_router(request.router, prefix="/api/v1")  # type: ignore
app.include_router(ground_station.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(satellite.router, prefix="/api/v1")
app.include_router(exclusion_cone.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")

# Added by MD
app.include_router(schedule.router, prefix="/api/v1") 
app.include_router(metrics.router, prefix="/api/v1")  


@app.get("/", include_in_schema=False)
async def root():
    logger.info("Root endpoint")
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Star Sync API")
