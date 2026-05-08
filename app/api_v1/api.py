from fastapi import APIRouter, FastAPI

from api_v1 import hashstore

# Bundle routers for the API
router = APIRouter()
router.include_router(hashstore.router, prefix="", tags=["data"])


def lifespan(app: FastAPI):
    """Called from the app lifepsan startup.

    Set application long lived state
    """
    app.state.hashstore = hashstore.get_hashstore_instance()
