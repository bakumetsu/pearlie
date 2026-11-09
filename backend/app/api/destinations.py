"""Destinations router – maps sites to Stash library folders."""

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.models import DestinationItem, Destinations, FolderBody
from app.targets import destinations
from app.targets.destinations import DestinationError
from app.targets.stash_client import StashError

router = APIRouter(prefix="/api")

FIXTURE_LIBRARY_PATHS = [
    "/mnt/media/stash/rule34",
    "/mnt/media/stash/rule34video",
    "/mnt/media/stash/Other",
]


def _library_paths(request: Request) -> list[str]:
    client = request.app.state.stash
    if client is not None:
        try:
            return client.library_paths()
        except StashError as err:
            raise ApiError(err.status, err.code, err.message) from None
    if request.app.state.settings.mode == "fixture":
        return FIXTURE_LIBRARY_PATHS
    raise ApiError(502, "not_configured", "Stash is not configured")


def _sites(request: Request) -> list[str]:
    return [
        sid
        for sid, src in request.app.state.sources.items()
        if src.target == "stash"
    ]


def _validated(request: Request, folder: str) -> str:
    settings = request.app.state.settings
    try:
        return destinations.validate_folder(
            folder,
            _library_paths(request),
            settings.stash_path_prefix_pearlie,
            settings.stash_path_prefix_stash,
        )
    except DestinationError as err:
        raise ApiError(err.status, err.code, err.message) from None


def _payload(request: Request) -> Destinations:
    settings = request.app.state.settings
    default = destinations.get_default(
        settings.db_path, settings.stash_default_dir.as_posix()
    )
    rows = destinations.list_destinations(settings.db_path)
    items = [DestinationItem(**row) for row in rows]
    return Destinations(default_folder=default, items=items)


@router.get("/destinations", response_model=Destinations)
def get_destinations(request: Request) -> Destinations:
    return _payload(request)


@router.put("/destinations/default", response_model=Destinations)
def put_default(body: FolderBody, request: Request) -> Destinations:
    validated = _validated(request, body.folder)
    settings = request.app.state.settings
    destinations.set_default(settings.db_path, validated)
    return _payload(request)


@router.put("/destinations/{site}", response_model=Destinations)
def put_destination(body: FolderBody, request: Request, site: str) -> Destinations:
    if site not in _sites(request):
        raise ApiError(422, "invalid", f"Unknown site {site}", field="site")
    validated = _validated(request, body.folder)
    settings = request.app.state.settings
    destinations.set_destination(settings.db_path, site, validated)
    return _payload(request)


@router.delete("/destinations/{site}", response_model=Destinations)
def delete_destination(request: Request, site: str) -> Destinations:
    if site not in _sites(request):
        raise ApiError(422, "invalid", f"Unknown site {site}", field="site")
    settings = request.app.state.settings
    if not destinations.delete_destination(settings.db_path, site):
        raise ApiError(404, "not_found", "No destination for that site")
    return _payload(request)
