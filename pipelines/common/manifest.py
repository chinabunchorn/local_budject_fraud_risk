"""Corpus manifest — the bridge between MinIO objects and catalog rows.

`manifest.yaml` lives at the corpus bucket root. Three document scopes mirror
migration 0003 (see docs/DATA_TEAM_GUIDE.md):

    reference_documents:                  # เอกสารกลาง — no owner
      - key: reference/กรมบัญชีกลาง/บัญชีค่าแรงงาน.pdf
        doc_type: reference_standard
    sub_districts:
      - name_th: ตำบลหัวเขา
        district_th: เดิมบางนางบวช
        province_th: สุพรรณบุรี
        budget_reports:                   # รายงานงบประมาณ — sub-district scope
          - key: ตำบลหัวเขา/budget_reports/รายงานงบ66.pdf
            doc_type: budget_report
        projects:
          - name_th: โครงการก่อสร้างถนน...
            fiscal_year: 2568             # พ.ศ.
            budget_total: 1500000.00      # OPTIONAL — extracted later, never invented
            category_th: โครงสร้างพื้นฐาน    # optional
            documents:
              - key: ตำบลหัวเขา/projects/2568/โครงการ.../bk01.pdf
                doc_type: bk01
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass(frozen=True)
class ManifestDocument:
    key: str
    doc_type: str | None = None


@dataclass(frozen=True)
class ManifestProject:
    name_th: str
    fiscal_year: int
    budget_total: float | None = None
    category_th: str | None = None
    documents: list[ManifestDocument] = field(default_factory=list)


@dataclass(frozen=True)
class ManifestSubDistrict:
    name_th: str
    district_th: str
    province_th: str
    budget_reports: list[ManifestDocument] = field(default_factory=list)
    projects: list[ManifestProject] = field(default_factory=list)


@dataclass(frozen=True)
class Manifest:
    sub_districts: list[ManifestSubDistrict] = field(default_factory=list)
    reference_documents: list[ManifestDocument] = field(default_factory=list)


def _documents(raw: list[dict[str, Any]], seen_keys: set[str]) -> list[ManifestDocument]:
    documents: list[ManifestDocument] = []
    for doc in raw:
        key = doc["key"]
        if key in seen_keys:
            raise ValueError(f"duplicate document key in manifest: {key!r}")
        seen_keys.add(key)
        documents.append(ManifestDocument(key=key, doc_type=doc.get("doc_type")))
    return documents


def parse_manifest(raw_yaml: str) -> Manifest:
    data: Any = yaml.safe_load(raw_yaml)
    if not isinstance(data, dict) or "sub_districts" not in data:
        raise ValueError("manifest must be a mapping with a 'sub_districts' list")

    seen_keys: set[str] = set()
    reference_documents = _documents(data.get("reference_documents", []), seen_keys)

    sub_districts: list[ManifestSubDistrict] = []
    for sd in data["sub_districts"]:
        budget_reports = _documents(sd.get("budget_reports", []), seen_keys)
        projects: list[ManifestProject] = []
        for proj in sd.get("projects", []):
            documents = _documents(proj.get("documents", []), seen_keys)
            fiscal_year = int(proj["fiscal_year"])
            if not 2500 <= fiscal_year <= 2600:  # พ.ศ. sanity
                raise ValueError(f"fiscal_year must be พ.ศ. (2500-2600), got {fiscal_year}")
            budget_total = proj.get("budget_total")
            projects.append(
                ManifestProject(
                    name_th=proj["name_th"],
                    fiscal_year=fiscal_year,
                    budget_total=float(budget_total) if budget_total is not None else None,
                    category_th=proj.get("category_th"),
                    documents=documents,
                )
            )
        sub_districts.append(
            ManifestSubDistrict(
                name_th=sd["name_th"],
                district_th=sd["district_th"],
                province_th=sd["province_th"],
                budget_reports=budget_reports,
                projects=projects,
            )
        )
    return Manifest(sub_districts=sub_districts, reference_documents=reference_documents)
