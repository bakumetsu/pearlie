"""Destinations router – maps sites to Stash library folders."""

from fastapi import APIRouter, Request

from app.api.errors import ApiError
from app.models import DestinationItem, Destinations, FolderBody, MappingBody
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


def _mapping(request: Request) -> tuple[str, str, bool]:
    settings = request.app.state.settings
    return destinations.get_mapping(
        settings.db_path,
        settings.stash_path_prefix_pearlie,
        settings.stash_path_prefix_stash,
    )


def _validated(request: Request, folder: str) -> str:
    pp, ps, _env = _mapping(request)
    try:
        return destinations.validate_folder(folder, _library_paths(request), pp, ps)
    except DestinationError as err:
        raise ApiError(err.status, err.code, err.message) from None


def _payload(request: Request) -> Destinations:
    settings = request.app.state.settings
    default = destinations.get_default(
        settings.db_path, settings.stash_default_dir.as_posix()
    )
    rows = destinations.list_destinations(settings.db_path)
    items = [DestinationItem(**row) for row in rows]
    try:
        library = _library_paths(request)
        library_error = None
    except ApiError as err:
        library, library_error = [], err.message
    pp, ps, from_env = _mapping(request)
    return Destinations(
        default_folder=default,
        items=items,
        sites=_sites(request),
        library_paths=library,
        library_error=library_error,
        prefix_pearlie=pp,
        prefix_stash=ps,
        prefix_from_env=from_env,
    )


@router.get("/destinations", response_model=Destinations)
def get_destinations(request: Request) -> Destinations:
    return _payload(request)


@router.put("/destinations/default", response_model=Destinations)
def put_default(body: FolderBody, request: Request) -> Destinations:
    validated = _validated(request, body.folder)
    settings = request.app.state.settings
    destinations.set_default(settings.db_path, validated)
    return _payload(request)


@router.put("/destinations/mapping", response_model=Destinations)
def put_mapping(body: MappingBody, request: Request) -> Destinations:
    try:
        pp, ps = destinations.validate_mapping(body.prefix_pearlie, body.prefix_stash)
    except DestinationError as err:
        raise ApiError(err.status, err.code, err.message) from None
    destinations.set_mapping(request.app.state.settings.db_path, pp, ps)
    return _payload(request)


@router.delete("/destinations/mapping", response_model=Destinations)
def delete_mapping(request: Request) -> Destinations:
    destinations.reset_mapping(request.app.state.settings.db_path)
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
