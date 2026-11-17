"""Model roster for the bench.

Source of truth: data/model_scores.csv (the ECI-ranked list: Epoch Capabilities
Index, OpenRouter display name, LiteLLM slug, ForecastBench name + overall
score). resolve_models.py maps each row to a concrete OpenRouter model id and
current pricing and writes starsim_causal/models.csv; this module loads that.
Every model is called through OpenRouter (litellm "openrouter/<id>") so all 24
share one API path and one set of defaults.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROSTER = HERE / "models.csv"


@dataclass(frozen=True)
class Model:
    openrouter_id: str
    name: str
    eci: float
    fb_name: str | None
    fb_overall: float | None
    context_length: int
    prompt_usd_per_m: float
    completion_usd_per_m: float
    reasoning_capable: bool
    max_completion_tokens: int | None = None   # provider's output cap from the catalog, if known

    @property
    def slug(self) -> str:
        """Filesystem-safe id."""
        return self.openrouter_id.replace("/", "__")


def _f(x: str) -> float | None:
    return float(x) if x not in ("", None) else None


def load_roster(select: str | None = None) -> list[Model]:
    """All roster models sorted by ECI ascending.

    select: None/"all" for everything, else a comma-separated list of
    OpenRouter ids (exact) or substrings (e.g. "claude,gpt-5-nano").
    """
    if not ROSTER.exists():
        raise SystemExit(f"{ROSTER} missing — run: uv run python results/causal/starsim_causal/resolve_models.py")
    models = []
    with open(ROSTER) as fh:
        for r in csv.DictReader(fh):
            models.append(Model(
                openrouter_id=r["openrouter_id"], name=r["name"], eci=float(r["eci"]),
                fb_name=r["fb_name"] or None, fb_overall=_f(r["fb_overall"]),
                context_length=int(r["context_length"]),
                prompt_usd_per_m=float(r["prompt_usd_per_m"]),
                completion_usd_per_m=float(r["completion_usd_per_m"]),
                reasoning_capable=r["reasoning_capable"].lower() == "true",
                max_completion_tokens=int(r["max_completion_tokens"]) if r.get("max_completion_tokens") else None))
    models.sort(key=lambda m: m.eci)
    if select and select != "all":
        wants = [w.strip() for w in select.split(",") if w.strip()]
        picked = []
        for w in wants:
            hits = [m for m in models if m.openrouter_id == w] or \
                   [m for m in models if w in m.openrouter_id]
            if not hits:
                raise SystemExit(f"--models: no roster model matches {w!r}")
            picked.extend(h for h in hits if h not in picked)
        models = sorted(picked, key=lambda m: m.eci)
    return models


def by_id() -> dict[str, Model]:
    return {m.openrouter_id: m for m in load_roster()}
