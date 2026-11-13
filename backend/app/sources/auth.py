"""Per-site credentials turned into request parts, shared by Test and the adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_USER_AGENT = "Pearlie/0.1"


@dataclass(frozen=True)
class SiteAuth:
    params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    basic: tuple[str, str] | None = None
    missing: tuple[str, ...] = ()  # labels of fields a half-filled pair still needs


def build_auth(site: str, values: Mapping[str, str]) -> SiteAuth:
    """Request parts for a site from its stored fields.

    A pair with only one field set is not sent (missing lists the other one);
    with nothing set the request stays anonymous. nhentai has no pair: the cookie
    alone is sent.
    """
    if site == "danbooru":
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        login, key = values.get("login", ""), values.get("api_key", "")
        if login and key:
            return SiteAuth(headers=headers, basic=(login, key))
        if login:
            return SiteAuth(headers=headers, missing=("API key",))
        if key:
            return SiteAuth(headers=headers, missing=("Login",))
        return SiteAuth(headers=headers)
    if site in ("gelbooru", "rule34"):
        uid, key = values.get("user_id", ""), values.get("api_key", "")
        if uid and key:
            return SiteAuth(params={"user_id": uid, "api_key": key})
        if uid:
            return SiteAuth(missing=("API key",))
        if key:
            return SiteAuth(missing=("User ID",))
        return SiteAuth()
    if site == "nhentai":
        cookie, agent = values.get("cookie", ""), values.get("user_agent", "")
        # A cookie saved before the User-Agent field existed keeps working with the default one.
        headers = {"User-Agent": agent or DEFAULT_USER_AGENT} if (agent or cookie) else {}
        if cookie:
            headers["Cookie"] = cookie
        return SiteAuth(headers=headers)
    return SiteAuth()
