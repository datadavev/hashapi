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


def split_pid(pid: str) -> tuple[str, list[str], str]:
    pid = pid.strip()
    parts = pid.split(" ", 1)
    path = ""
    path_parts = []
    if len(parts) > 1:
        path = parts[1].strip()
        if path in ("", ".", hashstore.folderentry.PATH_DELIMITER):
            path = ""
        path_parts = path.split(hashstore.folderentry.PATH_DELIMITER)
    pid = parts[0]
    folder_pid = f"{pid} {path}" if path != "" else pid
    return (pid, path_parts, folder_pid)


def resolve_pidpath(hs: hashstore.HashStore, pid: str, path: list[str]):
    pathpid = pid
    if len(path) > 0:
        pathpid = f"{pid} {hashstore.folderentry.PATH_DELIMITER.join(path)}"
    # First try grabbing the full path.
    try:
        print(f"TRY 1 {pathpid}")
        return hs.find_object(pathpid)
    except hashstore.filehashstore_exceptions.PidRefsDoesNotExist:
        pass
    try:
        print(f"TRY 2 {pathpid}")
        return hs.find_object(path[0])
    except hashstore.filehashstore_exceptions.PidRefsDoesNotExist:
        pass
    if len(path) == 0:
        raise hashstore.filehashstore_exceptions.PidRefsDoesNotExist(
            f"Unable to resolve {pathpid}"
        )
    print(f"TRY 3 {pathpid}")
    return resolve_pidpath(hs, path[0], path[1:])


@router.get("/info/{pid:path}")
async def file_info(pid: str, hs=Depends(get_hashstore)):
    """Return information for request debugging."""
    pid, path, folder_pid = split_pid(pid)
    object_info_dict = hs.find_object(folder_pid)
    media_type = get_media_type(object_info_dict.get("cid_object_path"))
    return {
        "pid": pid,
        "folder_pid": folder_pid,
        "path": path,
        "media_type": media_type,
        "object_info": object_info_dict,
    }


@router.get("/meta/{pid:path}")
async def system_metadata(pid: str, hs=Depends(get_hashstore)):
    """Return system metadata for specified PID+PATH.

    If system metadata is not available for the specified PID+PATH, then
    system metadata for the PID is returned.

    Return of the actual file is delegated to Apache mod_xsendfile.
    """
    pid, path, folder_pid = split_pid(pid)
    object_info_dict = hs.find_object(folder_pid)
    sys_meta_path = object_info_dict.get("sysmeta_path")
    if sys_meta_path in [None, "Does not exist."]:
        object_info_dict = hs.find_object(pid)
        sys_meta_path = object_info_dict.get("sysmeta_path")
        if sys_meta_path in [None, "Does not exist."]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"System Metadata for {folder_pid} not found.",
            )
    media_type = "application/xml"
    return Response(
        headers={
            "X-Sendfile": str(sys_meta_path),
            "Content-Type": media_type,
        }
    )


@router.head("/object/{pid:path}")
@router.get("/object/{pid:path}")
async def download_file(pid: str, hs=Depends(get_hashstore)):
    """Return the object at the specified PID+PATH
    Return of the actual file is delegated to Apache mod_xsendfile.
    """
    # Instead of returning the file, we tell Apache where it is
    pid, path, folder_pid = split_pid(pid)
    object_info_dict = resolve_pidpath(hs, pid, path)
    object_path = object_info_dict.get("cid_object_path")
    if isinstance(object_path, str):
        media_type = get_media_type(object_path)
    else:
        media_type = ""

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
