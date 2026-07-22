"""Shared fixtures. DB-backed tests skip cleanly when the stack is down."""

import pytest
from sqlalchemy import create_engine, text

from common.settings import database_url


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(database_url())
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL not reachable — start the compose stack and source .env")
    yield eng
    eng.dispose()


@pytest.fixture()
def project_id(engine):
    """A throwaway sub-district + project; cascades away on cleanup."""
    with engine.begin() as conn:
        sd_id = conn.execute(
            text(
                "INSERT INTO sub_districts (name_th, district_th, province_th) "
                "VALUES ('ตำบลทดสอบกอร์ดเรล', 'อำเภอทดสอบ', 'จังหวัดทดสอบ') RETURNING id"
            )
        ).scalar_one()
        pid = conn.execute(
            text(
                "INSERT INTO projects (sub_district_id, name_th, fiscal_year, budget_total) "
                "VALUES (:sd, 'โครงการทดสอบกอร์ดเรล', 2569, 998000) RETURNING id"
            ),
            {"sd": sd_id},
        ).scalar_one()
    yield str(pid)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sub_districts WHERE id = :id"), {"id": sd_id})
