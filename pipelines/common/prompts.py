"""Versioned prompt loader — templates live as files, never inline strings.

`load_risk_scoring("v1")` returns the assembled bundle;
`bundle.version` ("risk_scoring/v1") is what goes into
`RiskResult.prompt_version`, keeping Langfuse traces reproducible. Old
version directories are never edited — a template change is a new directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from schemas import RiskFactorType

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

_PLACEHOLDER = re.compile(r"\{(\w+)\}")

USER_TEMPLATE_FIELDS = frozenset(
    {
        "sub_district",
        "project_name",
        "fiscal_year",
        "budget_total",
        "budget_lines",
        "document_excerpts",
        "regulation_context",
        "factor_definitions",
    }
)


@dataclass(frozen=True)
class PromptBundle:
    version: str  # e.g. "risk_scoring/v1" — recorded as RiskResult.prompt_version
    system: str
    user_template: str
    factors: dict[RiskFactorType, str]


def load_risk_scoring(version: str = "v1") -> PromptBundle:
    root = PROMPTS_DIR / "risk_scoring" / version
    if not root.is_dir():
        raise FileNotFoundError(f"no such prompt version: risk_scoring/{version}")

    factors: dict[RiskFactorType, str] = {}
    for factor_type in RiskFactorType:
        path = root / "factors" / f"{factor_type.value.lower()}.md"
        if not path.exists():
            raise FileNotFoundError(f"missing factor template: {path}")
        factors[factor_type] = path.read_text(encoding="utf-8").strip()

    user_template = (root / "user.md").read_text(encoding="utf-8").strip()
    unknown = set(_PLACEHOLDER.findall(user_template)) - USER_TEMPLATE_FIELDS
    if unknown:
        raise ValueError(f"user.md has unknown placeholders: {sorted(unknown)}")

    return PromptBundle(
        version=f"risk_scoring/{version}",
        system=(root / "system.md").read_text(encoding="utf-8").strip(),
        user_template=user_template,
        factors=factors,
    )


def build_messages(
    bundle: PromptBundle,
    *,
    sub_district: str,
    project_name: str,
    fiscal_year: int,
    budget_total: str,
    budget_lines: str,
    document_excerpts: str,
    regulation_context: str,
) -> list[dict[str, str]]:
    """OpenAI-style messages for the vLLM client (guided_json is bound by the
    caller to schemas.RiskAssessment; temperature 0)."""
    user = bundle.user_template.format(
        sub_district=sub_district,
        project_name=project_name,
        fiscal_year=fiscal_year,
        budget_total=budget_total,
        budget_lines=budget_lines,
        document_excerpts=document_excerpts,
        regulation_context=regulation_context,
        factor_definitions="\n\n".join(bundle.factors[ft] for ft in RiskFactorType),
    )
    return [
        {"role": "system", "content": bundle.system},
        {"role": "user", "content": user},
    ]
