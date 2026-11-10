from app.filters.aliases import fold
from app.fixtures import data
from app.models import BaseList, RuleMapping, RulesBody, RulesPut, RulesTestResult, Tag


class Stale(Exception):
    pass


class RulesInvalid(Exception):
    def __init__(self, field: str, msg: str):
        super().__init__(msg)
        self.field = field


def _hit(rule: str, tags: list[Tag]) -> bool:
    if ":" in rule:
        scope, value = rule.split(":", 1)
        fs, fv = fold(scope), fold(value)
        return any(t.scope is not None and fold(t.scope) == fs and fold(t.name) == fv for t in tags)
    fr = fold(rule)
    return any(fold(t.name) == fr for t in tags)


class Rules:
    def __init__(self):
        self.reset()

    def reset(self):
        self.version = 1
        self.reject = ["reject_alpha"]
        self.warn = ["warn_alpha", "warn_beta"]
        self.require = []
        self.mapping = [RuleMapping(pattern="artist:*", to="stash_tag")]

    def get(self) -> RulesBody:
        return RulesBody(
            version=self.version,
            reject=list(self.reject),
            warn=list(self.warn),
            require=list(self.require),
            mapping=list(self.mapping),
            base_list=BaseList(tags=data.BASE_LIST),
        )

    def put(self, body: RulesPut) -> RulesBody:
        if body.version != self.version:
            raise Stale("version mismatch")
        for field in ("reject", "warn", "require"):
            for rule in getattr(body, field):
                if not rule or len(rule) > 64:
                    raise RulesInvalid(field, f"rule must be 1–64 chars: {rule!r}")
        for m in body.mapping:
            if not m.pattern:
                raise RulesInvalid("mapping", f"pattern must not be empty: {m.pattern!r}")
        self.reject = list(body.reject)
        self.warn = list(body.warn)
        self.require = list(body.require)
        self.mapping = list(body.mapping)
        self.version += 1
        return self.get()

    def test(self, tags: list[str]) -> RulesTestResult:
        parsed: list[Tag] = []
        for name in tags:
            if ":" in name:
                scope, val = name.split(":", 1)
                parsed.append(Tag(name=val, scope=scope))
            else:
                parsed.append(Tag(name=name, scope=None))
        for base_tag in data.BASE_LIST:
            if _hit(base_tag, parsed):
                return RulesTestResult(decision="reject", layer="base", rule=base_tag)
        for rule in self.reject:
            if _hit(rule, parsed):
                return RulesTestResult(decision="reject", layer="reject", rule=rule)
        if self.require and not any(_hit(r, parsed) for r in self.require):
            return RulesTestResult(
                decision="require_missing", layer="require", rule=self.require[0]
            )
        for rule in self.warn:
            if _hit(rule, parsed):
                return RulesTestResult(decision="warn", layer="warn", rule=rule)
        return RulesTestResult(decision="allow")


rules = Rules()
