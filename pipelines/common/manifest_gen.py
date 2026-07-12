"""Manifest generator: corpus catalog → manifest.yaml (Phase C).

The data team's tree carries everything except each sub-district's
อำเภอ/จังหวัด, which live in SUB_DISTRICT_INFO (confirmed with the data team,
2026-07-12). budget_total is deliberately absent — it gets extracted from
บก.01 / budget reports in the structured-extraction phase, never invented.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from common.corpus_catalog import CorpusFile, walk_corpus

# ตำบล → (อำเภอ, จังหวัด) — from the data team, 2026-07-12
SUB_DISTRICT_INFO: dict[str, tuple[str, str]] = {
    "ตำบลหัวเขา": ("เดิมบางนางบวช", "สุพรรณบุรี"),
    "ตำบลท่าช้าง": ("บางกล่ำ", "สงขลา"),
}


def generate_manifest(entries: list[CorpusFile]) -> str:
    unknown = sorted(
        {e.sub_district for e in entries if e.sub_district} - set(SUB_DISTRICT_INFO)
    )
    if unknown:
        raise ValueError(
            f"sub-districts missing from SUB_DISTRICT_INFO: {unknown} — "
            "ask the data team for their อำเภอ/จังหวัด"
        )

    reference_documents = [
        {"key": e.normalized_key, "doc_type": e.doc_type}
        for e in entries
        if e.scope == "REFERENCE"
    ]

    sub_districts = []
    for name in sorted({e.sub_district for e in entries if e.sub_district}):
        district, province = SUB_DISTRICT_INFO[name]
        budget_reports = [
            {"key": e.normalized_key, "doc_type": e.doc_type}
            for e in entries
            if e.scope == "SUB_DISTRICT" and e.sub_district == name
        ]
        project_keys = sorted(
            {
                (e.fiscal_year, e.project_name)
                for e in entries
                if e.scope == "PROJECT" and e.sub_district == name
            }
        )
        projects = []
        for fiscal_year, project_name in project_keys:
            documents = [
                {"key": e.normalized_key, "doc_type": e.doc_type}
                for e in entries
                if e.scope == "PROJECT"
                and e.sub_district == name
                and e.fiscal_year == fiscal_year
                and e.project_name == project_name
            ]
            projects.append(
                {
                    "name_th": project_name,
                    "fiscal_year": fiscal_year,
                    "documents": documents,
                }
            )
        sub_districts.append(
            {
                "name_th": name,
                "district_th": district,
                "province_th": province,
                "budget_reports": budget_reports,
                "projects": projects,
            }
        )

    return yaml.safe_dump(
        {"reference_documents": reference_documents, "sub_districts": sub_districts},
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )


def generate_from_tree(root: Path) -> str:
    return generate_manifest(walk_corpus(root))


if __name__ == "__main__":
    import sys

    default_root = "../data/corpus/real_data"
    print(generate_from_tree(Path(sys.argv[1] if len(sys.argv) > 1 else default_root)))
