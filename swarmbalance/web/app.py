"""FastAPI assembly; business operations and routes live in dedicated modules."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from swarmbalance.contracts.errors import ApplicationError
from swarmbalance.web.dependencies import runtime
from swarmbalance.web.routes import pages, metadata, simulation, tasks, fleet, checkpoints, scenarios, configuration, comparison, gis

app = FastAPI(title="无人机调度仿真控制台")
# GIS was registered first in the existing application; retain route ordering.
for module in (gis, pages, metadata, simulation, tasks, fleet, checkpoints, scenarios, configuration, comparison):
    app.include_router(module.router)


@app.exception_handler(ApplicationError)
async def application_error(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.on_event("startup")
def _warmup_session():
    runtime.warmup()
