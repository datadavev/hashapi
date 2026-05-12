"""Implements a FastAPI router for access to a HashStore instance."""

import json
import pathlib

import hashstore
import hashstore.filehashstore_exceptions
import hashstore.folderentry
import magic
import pyarrow.parquet
import yaml
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader


HASHSTORE_PATH = pathlib.Path("/var/data/hashstore")
HS_MODULE_NAME = "hashstore.filehashstore"
HS_CLASS_NAME = "FileHashStore"
WEB_DELIMITER = "|"


def split_pidpath(pidpath: str, delimiter: str = "|") -> list[str]:
    pathpid = pidpath.strip(delimiter)
    parts = pathpid.split(delimiter)
    return parts


def get_media_type(path: str) -> str:
    try:
        pyarrow.parquet.read_schema(path)
        return "application/vnd.apache.parquet"
    except Exception:
        pass
    return magic.from_file(path, mime=True)


def load_hashstore_properties(path: pathlib.Path) -> dict:
    properties_file = path / "hashstore.yaml"
    if not properties_file.exists():
        raise FileNotFoundError(
            f"Hashstore properties file not found: {properties_file}"
        )
    with open(properties_file, "r") as f:
        properties = yaml.load(f, Loader=Loader)
    properties["store_path"] = str(path)
    return properties


def get_hashstore_instance() -> hashstore.HashStore:
    properties = load_hashstore_properties(HASHSTORE_PATH)
    hashstore_factory = hashstore.HashStoreFactory()
    hash_store = hashstore_factory.get_hashstore(
        HS_MODULE_NAME, HS_CLASS_NAME, properties
    )
    return hash_store


router = APIRouter()


def get_hashstore(request: Request):
    return request.app.state.hashstore


@router.get("/info/{pid:path}")
async def file_info(pid: str, hs=Depends(get_hashstore)):
    """Return information for request debugging."""
    path = hashstore.folderentry.split_pidpath(pid, delimiter=WEB_DELIMITER)
    try:
        object_info_dict = hs.resolve_pidpath(path)
        media_type = get_media_type(object_info_dict.get("cid_object_path"))
        return {
            "pid": pid,
            "path": path,
            "media_type": media_type,
            "object_info": object_info_dict,
        }
    except hashstore.filehashstore_exceptions.PidRefsDoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Not Found", "pid": pid},
        )


@router.get("/meta/{pid:path}")
async def system_metadata(pid: str, hs=Depends(get_hashstore)):
    """Return system metadata for specified PID+PATH.

    If system metadata is not available for the specified PID+PATH, then
    system metadata for the PID is returned.

    Return of the actual file is delegated to Apache mod_xsendfile.
    """
    path = hashstore.folderentry.split_pidpath(pid, delimiter=WEB_DELIMITER)
    try:
        object_info_dict = hs.resolve_pidpath(path)
        sys_meta_path = object_info_dict.get("sysmeta_path")
        if sys_meta_path in [None, "Does not exist."]:
            object_info_dict = hs.find_object(pid)
            sys_meta_path = object_info_dict.get("sysmeta_path")
            if sys_meta_path in [None, "Does not exist."]:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"System Metadata for {pid} not found.",
                )
        media_type = "application/xml"
        return Response(
            headers={
                "X-Sendfile": str(sys_meta_path),
                "Content-Type": media_type,
            }
        )
    except hashstore.filehashstore_exceptions.PidRefsDoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Not Found", "pid": pid},
        )


@router.head("/object/{pid:path}")
@router.get("/object/{pid:path}")
async def download_file(pid: str, hs=Depends(get_hashstore)):
    """Return the object at the specified PID+PATH
    Return of the actual file is delegated to Apache mod_xsendfile.
    """
    # Instead of returning the file, we tell Apache where it is
    path = hashstore.folderentry.split_pidpath(pid, delimiter=WEB_DELIMITER)
    try:
        object_info_dict = hs.resolve_pidpath(path)
        object_path = object_info_dict.get("cid_object_path")
        media_type = get_media_type(object_path)

        if media_type == "application/json":
            # peek at the file. If it's a proxy file, then
            # redirect to the designated URL
            with open(object_path, "r") as fsrc:
                proxy_dict = json.load(fsrc)
                redirect_url = proxy_dict.get("url")
                if redirect_url is not None:
                    return RedirectResponse(
                        url=redirect_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
                    )
        return Response(
            headers={
                "X-Sendfile": str(object_path),
                "Content-Type": media_type,
            }
        )
    except hashstore.filehashstore_exceptions.PidRefsDoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Not Found", "pid": pid},
        )
