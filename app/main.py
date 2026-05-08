from contextlib import asynccontextmanager

from fastapi import FastAPI

import api_v1.api


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Do this in a lifespan context to avoid having to reload config
    # etc for every request. The hash_store instance is made available
    # from requests with the app.state.hs variable
    #
    api_v1.api.lifespan(app)
    yield
    # hashstore instance is released here


app = FastAPI(title="hashapi", lifespan=lifespan)

app.include_router(api_v1.api.router, prefix="/v1")


@app.get("/")
def read_root():
    return {"status": "FastAPI is running behind Apache"}
