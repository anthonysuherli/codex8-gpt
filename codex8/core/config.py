"""Runtime configuration.

Two layers, kept deliberately separate:

* ``Settings`` — secrets and environment-bound identity. Read from the process
  environment / ``.env`` via pydantic-settings. These never belong in a
  checked-in file.
* ``AppConfig`` — tunable knobs (model names, temperatures, search limits,
  similarity thresholds, prompts). Loaded from a human-editable YAML file so
  they can be changed without touching code or redeploying.

``AppConfig`` precedence, lowest to highest:

    built-in defaults  <  config.yaml  <  environment variables

Environment overrides use the ``C8_<SECTION>__<FIELD>`` form, e.g.
``C8_TIERS__RICH_HIT_COUNT=7`` or ``C8_SEARCH__MIN_SIMILARITY=0.2``.

The YAML file location defaults to the repo-root ``config.yaml`` and can be
pointed elsewhere with the ``CODEX8_CONFIG_FILE`` environment variable.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Secrets + deployment identity. One credential: the OpenAI API key."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore"
    )

    openai_api_key: str | None = None
    codex8_db_path: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


DEFAULT_SYSTEM_PROMPT = """\
You are Codex8 — an agent that helps the user grow a knowledge base.

You have a set of tools that operate against the user's active KB. When the
user expresses intent that maps to a tool, call it. Otherwise reply
conversationally.

When a tool runs, narrate briefly what happened (don't restate the full
result; the UI shows tool cards inline).

Your messages already include a <preamble> of current KB context (a synopsis
plus query-relevant findings) and a coverage verdict; consult it before calling
explore.

Available tools and when to use them:
  - explore(query, mode): research/recall the KB. mode=auto (KB first, web if
    thin), recall (KB-only), research (force web). Findings persist to the KB.
  - ingest_file(upload_id): process an uploaded file (PDF / MD / TXT)
  - kg_view(focus?): open the knowledge graph viewer
  - deploy_kb(): publish the KB as a context API, mint an API key

Be concise. Use markdown sparingly.
"""

DEFAULT_TOOL_DESCRIPTIONS: dict[str, str] = {
    "explore": (
        "Unified knowledge tool. mode=auto: search the KB first and only research "
        "the web if coverage is thin; recall: KB-only semantic search (no web); "
        "research: force the full web research pipeline. depth controls breadth. "
        "New findings persist to the active KB. Use whenever the user wants to look "
        "something up, learn, or research a topic."
    ),
    "ingest_file": (
        "Process an uploaded file (PDF / MD / TXT) — extract text, chunk into "
        "findings, embed, and persist to the knowledge base."
    ),
    "kg_view": "Open the knowledge graph viewer. Optionally focus on a concept.",
    "deploy_kb": (
        "Publish the active KB as a context API. Flips published=true, mints a new "
        "API key, and returns the key (shown to the user once)."
    ),
}


class SearchConfig(BaseModel):
    """`explore` recall + shared retrieval knobs."""

    default_limit: int = 10
    max_limit: int = 50
    min_similarity: float = 0.0
    max_finding_chunks: int = 25


class TiersConfig(BaseModel):
    """Similarity-band thresholds + always-on preamble budget."""

    band1_min: float = 0.55
    band2_min: float = 0.40
    band3_min: float = 0.25
    rich_hit_count: int = 3
    preamble_char_budget: int = 7000


class SynopsisConfig(BaseModel):
    """Per-KB synopsis spine: build model + incremental regen triggers."""

    model: str = "gpt-5.6-luna"  # cheap/fast tier
    rebuild_delta: int = 15
    rebuild_max_age_hours: int = 168
    max_entries: int = 6


class ExplorationConfig(BaseModel):
    """`explore` tool + research pipeline knobs.

    Models are OpenAI API model IDs.
    """

    planner_model: str = "gpt-5.6-terra"
    extraction_model: str = "gpt-5.6-terra"
    extraction_fallback_model: str = "gpt-5.6-luna"
    research_model: str = "gpt-5.6-luna"  # drives the hosted web_search tool
    temperature: float = 0.0
    reasoning_effort: str | None = None

    search_mode: str = "auto"

    @field_validator("search_mode")
    @classmethod
    def _check_search_mode(cls, v: str) -> str:
        if v not in {"auto", "agent", "tavily"}:
            raise ValueError(f"search_mode must be auto|agent|tavily, got {v!r}")
        return v

    search_depth: str = "advanced"
    max_results_per_query: int = 20
    fallback_result_threshold: int = 5
    expansion_result_threshold: int = 3
    max_concurrent_searches: int = 6

    max_pages: int = 15
    max_concurrent_extractions: int = 10
    max_content_per_page: int = 100_000

    enable_evaluation: bool = True
    evaluation_model: str = "gpt-5.6-terra"

    fuzzy_match_threshold: float = 0.80
    min_confidence_threshold: float = 0.2

    default_max_findings: int = 12
    max_findings: int = 40


class NarrationConfig(BaseModel):
    """Per-phase narration: a cheap OpenAI API line per pipeline phase."""

    enabled: bool = True
    model: str = "gpt-5.6-luna"
    temperature: float = 0.3
    max_tokens: int = 60


class OKFConfig(BaseModel):
    """OKF concept-doc synthesis: one OpenAI API pass that rewrites an entity's
    grounded findings into a readable prose document."""

    model: str = "gpt-5.6-terra"
    temperature: float = 0.3
    max_tokens: int = 900


class DeepenConfig(BaseModel):
    """Autonomous gap-following deep-research (`deepen`) knobs.

    Hybrid loop oracle: an LLM critic steers next facets; depth_cap + a
    coverage floor terminate. Models use OpenAI API model IDs.
    """

    depth_cap: int = 3
    min_rounds: int = 1
    coverage_target: float = 0.8
    facets_per_round: int = 4
    max_concurrent_facets: int = 4

    decompose_model: str = "gpt-5.6-terra"
    critic_model: str = "gpt-5.6-terra"
    temperature: float = 0.0
    reasoning_effort: str | None = None

    @model_validator(mode="after")
    def _clamp_min_rounds(self) -> DeepenConfig:
        if self.min_rounds > self.depth_cap:
            self.min_rounds = self.depth_cap
        return self


class EmbeddingConfig(BaseModel):
    """Embedding client + chunking knobs."""

    model: str = "text-embedding-3-small"
    dim: int = 1536
    input_char_cap: int = 8192
    chunk_max_chars: int = 1800


class KnowledgeGraphConfig(BaseModel):
    """KG build (extract entities/relations from findings → kg_nodes/kg_edges).

    Models are OpenAI API model IDs, like ExplorationConfig.
    """

    extraction_model: str = "gpt-5.6-terra"
    extraction_fallback_model: str = "gpt-5.6-luna"
    temperature: float = 0.0
    reasoning_effort: str | None = None

    max_findings: int = 120
    max_finding_chars: int = 1200
    node_match_threshold: float = 0.86
    max_nodes: int = 400
    max_edges: int = 1200


class ConceptsConfig(BaseModel):
    """Domain-concept (glossary) extraction knobs (OpenAI API model IDs)."""

    extract_model: str = "gpt-5.6-terra"
    max_findings_context: int = 60
    max_finding_chars: int = 1200
    max_terms: int = 40


class PromptsConfig(BaseModel):
    """Agent system prompt + per-tool descriptions surfaced to the LLM."""

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    tool_descriptions: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_TOOL_DESCRIPTIONS)
    )


class AppConfig(BaseModel):
    """Aggregate of all tunable sections."""

    search: SearchConfig = Field(default_factory=SearchConfig)
    tiers: TiersConfig = Field(default_factory=TiersConfig)
    synopsis: SynopsisConfig = Field(default_factory=SynopsisConfig)
    exploration: ExplorationConfig = Field(default_factory=ExplorationConfig)
    narration: NarrationConfig = Field(default_factory=NarrationConfig)
    okf: OKFConfig = Field(default_factory=OKFConfig)
    deepen: DeepenConfig = Field(default_factory=DeepenConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    knowledge_graph: KnowledgeGraphConfig = Field(default_factory=KnowledgeGraphConfig)
    concepts: ConceptsConfig = Field(default_factory=ConceptsConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)


_ENV_PREFIX = "C8_"
_NESTED_DELIM = "__"


def _config_path() -> Path:
    override = os.getenv("CODEX8_CONFIG_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "config.yaml"


def _load_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file {path} must contain a YAML mapping at the top level")
    return data


def _env_overrides() -> dict:
    """Collect `C8_<SECTION>__<FIELD>` env vars into a nested dict.

    Values stay as strings; Pydantic coerces them when validating AppConfig.
    """
    out: dict[str, dict] = {}
    for key, value in os.environ.items():
        if not key.startswith(_ENV_PREFIX) or _NESTED_DELIM not in key:
            continue
        section, _, field = key[len(_ENV_PREFIX) :].partition(_NESTED_DELIM)
        if not section or not field:
            continue
        out.setdefault(section.lower(), {})[field.lower()] = value
    return out


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Load the layered app config: defaults < config.yaml < env vars.

    Cached. Call ``get_config.cache_clear()`` after mutating the file or env
    (tests do this).
    """
    data: dict = {}
    _deep_merge(data, _load_file(_config_path()))
    _deep_merge(data, _env_overrides())
    return AppConfig.model_validate(data)
