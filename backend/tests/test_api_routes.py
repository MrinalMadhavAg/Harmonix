"""HTTP-level route tests.

Exists because a unit test on `parse_tabular` passed while the /ingest/upload
route raised TypeError on every call: the parser was covered, the endpoint
that calls it was not. These drive the routes through Starlette's TestClient
so signature and wiring errors surface.

Marked integration because the app's lifespan needs PostgreSQL and the model.
"""
from __future__ import annotations

import io

import pytest

pytestmark = pytest.mark.integration


def _database_available() -> bool:
    try:
        import psycopg

        from app.config import get_settings

        with psycopg.connect(get_settings().database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 - availability probe
        return False


pytest.importorskip("fastapi")
if not _database_available():
    pytest.skip("No PostgreSQL reachable; route tests skipped.", allow_module_level=True)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _csv(text: str) -> dict:
    return {"file": ("upload.csv", io.BytesIO(text.encode("utf-8")), "text/csv")}


class TestUploadRoute:
    def test_a_valid_upload_succeeds_end_to_end(self, client):
        import uuid

        code = f"RT-{uuid.uuid4().hex[:8].upper()}"
        r = client.post(
            "/ingest/upload",
            files=_csv(
                "cpse_org,legacy_code,description,commodity_type\n"
                f"ROUTECO,{code},GATE VALVE 6 INCH CARBON STEEL CLASS 150 FLANGED,gate_valve\n"
            ),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["report"]["inserted"] == 1
        assert body["job_id"]
        assert body["harmonization"]["golden_records"] > 0

    def test_progress_can_be_polled_by_job_id(self, client):
        import uuid

        code = f"RT-{uuid.uuid4().hex[:8].upper()}"
        r = client.post(
            "/ingest/upload",
            files=_csv(
                "cpse_org,legacy_code,description,commodity_type\n"
                f"ROUTECO,{code},PIPE SEAMLESS 6 INCH SCH 40 CARBON STEEL,pipe\n"
            ),
        )
        job_id = r.json()["job_id"]
        status = client.get(f"/ingest/jobs/{job_id}")
        assert status.status_code == 200
        assert status.json()["job_id"] == job_id
        assert status.json()["status"] == "SUCCEEDED"

    def test_unknown_job_id_is_404(self, client):
        assert client.get("/ingest/jobs/no-such-job").status_code == 404

    @pytest.mark.parametrize(
        "name,payload",
        [
            ("missing required column", "cpse_org,legacy_code\nBHEL,123\n"),
            ("header only", "cpse_org,legacy_code,description\n"),
            ("all rows blank", "cpse_org,legacy_code,description\n,,\n"),
        ],
    )
    def test_malformed_csv_returns_422_with_a_usable_message(self, client, name, payload):
        r = client.post("/ingest/upload", files=_csv(payload))
        assert r.status_code == 422, f"{name}: got {r.status_code} {r.text}"
        body = r.json()
        assert body["type"] == "validation_error"
        assert body["detail"] and "internal error" not in body["detail"].lower()

    def test_empty_file_returns_422(self, client):
        r = client.post(
            "/ingest/upload",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        )
        assert r.status_code == 422
        assert "empty" in r.json()["detail"].lower()

    def test_binary_garbage_returns_422_naming_the_file(self, client):
        r = client.post(
            "/ingest/upload",
            files={
                "file": (
                    "broken.xlsx",
                    io.BytesIO(b"\x00\x01\x02not-a-spreadsheet"),
                    "application/vnd.ms-excel",
                )
            },
        )
        assert r.status_code == 422
        assert "broken.xlsx" in r.json()["detail"]

    def test_duplicate_rows_succeed_and_are_reported(self, client):
        import uuid

        code = f"RT-{uuid.uuid4().hex[:8].upper()}"
        row = f"ROUTECO,{code},GATE VALVE DN150 CARBON STEEL CL150 FLANGED,gate_valve\n"
        r = client.post(
            "/ingest/upload",
            files=_csv("cpse_org,legacy_code,description,commodity_type\n" + row + row),
        )
        assert r.status_code == 200, r.text
        report = r.json()["report"]
        assert report["inserted"] == 1
        assert report["skipped_duplicates"] == 1
        assert report["warnings"]


class TestCoreRoutesRespond:
    @pytest.mark.parametrize(
        "path",
        [
            "/health", "/dashboard", "/materials?limit=2", "/golden-records?limit=2",
            "/review-queue?limit=2", "/cpses", "/commodities", "/reports/summary",
            "/reports/surplus", "/safety-blocks?limit=2", "/config/weights",
            "/config/safety", "/config/standards", "/config/settings", "/jobs",
            "/audit", "/index-status", "/ingest/template", "/steward-decisions",
            "/governance/overrides",
        ],
    )
    def test_get_returns_200(self, client, path):
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/materials/999999", 404),
            ("/crosswalk/NMI-999999", 404),
            ("/evidence/NMI-999999", 404),
            ("/cpses/NOSUCHCPSE", 404),
            ("/review-queue/999999", 404),
            ("/jobs/no-such-job", 404),
        ],
    )
    def test_missing_resources_are_404_not_500(self, client, path, expected):
        r = client.get(path)
        assert r.status_code == expected, f"{path} -> {r.status_code} {r.text[:200]}"
        assert "internal error" not in r.text.lower()


class TestMutatingRoutesValidateInput:
    def test_governance_rejects_a_blank_description(self, client):
        r = client.post("/check-new-material", json={"description": ""})
        assert r.status_code == 422

    def test_governance_override_rejects_an_unknown_nmi(self, client):
        r = client.post(
            "/governance/override",
            json={
                "description": "X", "decision": "USE_EXISTING",
                "suggested_nmi": "NMI-999999",
            },
        )
        assert r.status_code == 404
        assert "not a known" in r.json()["detail"]

    def test_governance_override_rejects_an_unknown_decision(self, client):
        r = client.post(
            "/governance/override", json={"description": "X", "decision": "NONSENSE"}
        )
        assert r.status_code == 400

    def test_weights_reject_an_unknown_commodity(self, client):
        r = client.put(
            "/config/weights/not_a_commodity",
            json={"semantic": 0.3, "lexical": 0.2, "attributes": 0.5},
        )
        assert r.status_code == 404

    def test_weights_reject_an_all_zero_split(self, client):
        r = client.put(
            "/config/weights/gate_valve",
            json={"semantic": 0, "lexical": 0, "attributes": 0},
        )
        assert r.status_code == 400

    def test_transfer_rejects_an_unknown_nmi(self, client):
        r = client.post(
            "/transfers",
            json={"nmi": "NMI-999999", "from_cpse": "BHEL", "to_cpse": "IOCL", "quantity": 1},
        )
        assert r.status_code == 404

    def test_transfer_rejects_identical_source_and_destination(self, client):
        r = client.post(
            "/transfers",
            json={"nmi": "NMI-000001", "from_cpse": "BHEL", "to_cpse": "BHEL", "quantity": 1},
        )
        assert r.status_code == 400

    def test_safety_toggle_runs_and_reports_its_setting(self, client):
        off = client.post("/harmonize", json={"enforce_safety": False})
        assert off.status_code == 200
        assert off.json()["stats"]["enforce_safety"] is False

        on = client.post("/harmonize", json={"enforce_safety": True})
        assert on.status_code == 200
        assert on.json()["stats"]["enforce_safety"] is True
        # Enforcement must actually change the outcome.
        assert on.json()["stats"]["golden_records"] > off.json()["stats"]["golden_records"]
        assert on.json()["stats"]["blocked_pairs"] > 0
