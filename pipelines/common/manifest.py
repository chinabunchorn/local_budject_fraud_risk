"""Corpus manifest — the bridge between MinIO objects and catalog rows.

`manifest.yaml` lives at the corpus bucket root and is the single place that
maps documents to their sub-district/project (documents.project_id is NOT
NULL — nothing ingests without a home):

    sub_districts:
      - name_th: เทศบาลตำบลท่าช้าง
        district_th: เมืองนครนายก
        province_th: นครนายก
        projects:
          - name_th: โครงการปรับปรุงถนนสายหลัก
            fiscal_year: 2567          # พ.ศ.
            budget_total: 1500000.00
            category_th: โครงสร้างพื้นฐาน   # optional
            documents:
              - key: tha-chang/road/contract.pdf   # MinIO object key
                doc_type: contract               # optional free label
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
    budget_total: float
    category_th: str | None = None
    documents: list[ManifestDocument] = field(default_factory=list)


@dataclass(frozen=True)
class ManifestSubDistrict:
    name_th: str
    district_th: str
    province_th: str
    projects: list[ManifestProject] = field(default_factory=list)


def parse_manifest(raw_yaml: str) -> list[ManifestSubDistrict]:
    data: Any = yaml.safe_load(raw_yaml)
    if not isinstance(data, dict) or "sub_districts" not in data:
        raise ValueError("manifest must be a mapping with a 'sub_districts' list")

    seen_keys: set[str] = set()
    sub_districts: list[ManifestSubDistrict] = []
    for sd in data["sub_districts"]:
        projects: list[ManifestProject] = []
        for proj in sd.get("projects", []):
            documents: list[ManifestDocument] = []
            for doc in proj.get("documents", []):
                key = doc["key"]
                if key in seen_keys:
                    raise ValueError(f"duplicate document key in manifest: {key!r}")
                seen_keys.add(key)
                documents.append(ManifestDocument(key=key, doc_type=doc.get("doc_type")))
            fiscal_year = int(proj["fiscal_year"])
            if not 2500 <= fiscal_year <= 2600:  # พ.ศ. sanity
                raise ValueError(f"fiscal_year must be พ.ศ. (2500-2600), got {fiscal_year}")
            projects.append(
                ManifestProject(
                    name_th=proj["name_th"],
                    fiscal_year=fiscal_year,
                    budget_total=float(proj["budget_total"]),
                    category_th=proj.get("category_th"),
                    documents=documents,
                )
            )
        sub_districts.append(
            ManifestSubDistrict(
                name_th=sd["name_th"],
                district_th=sd["district_th"],
                province_th=sd["province_th"],
                projects=projects,
            )
        )
    return sub_districts
