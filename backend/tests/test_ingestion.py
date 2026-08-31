"""Upload parsing and validation.

The parse step is the boundary where a user's messy file meets the pipeline,
so it must fail with a message they can act on rather than a stack trace.
"""
from __future__ import annotations

import io

import pytest

from app.services.ingestion import IngestValidationError, parse_tabular

GOOD = (
    "cpse_org,legacy_code,description,commodity_type,quantity,uom\n"
    "BHEL,10023841,GATE VALVE 6 INCH CS CLASS 150 FLANGED,gate_valve,12,NOS\n"
    "IOCL,MAT-GV-0284,GT VLV DN150 CARBON STEEL CL150 FLGD,gate_valve,7,NOS\n"
)


def parse(text: str, name: str = "upload.csv"):
    return parse_tabular(text.encode("utf-8"), name)


class TestHappyPath:
    def test_parses_rows(self):
        rows = parse(GOOD)
        assert len(rows) == 2
        assert rows[0].cpse_org == "BHEL"
        assert rows[0].legacy_code == "10023841"
        assert rows[0].commodity_type == "gate_valve"
        assert rows[0].quantity == 12
        assert rows[0].uom == "NOS"

    def test_cpse_is_upper_cased(self):
        rows = parse("cpse_org,legacy_code,description\nbhel,X1,GATE VALVE DN150\n")
        assert rows[0].cpse_org == "BHEL"

    def test_optional_columns_may_be_absent(self):
        rows = parse("cpse_org,legacy_code,description\nBHEL,X1,GATE VALVE DN150 CS CL150\n")
        assert rows[0].commodity_type is None
        assert rows[0].quantity is None

    @pytest.mark.parametrize(
        "header",
        [
            "cpse,material_code,material_description",
            "organisation,code,desc",
            "CPSE_Org,Legacy_Code,Description",
            "  cpse_org , legacy_code , description ",
        ],
    )
    def test_column_aliases_and_casing(self, header):
        rows = parse(f"{header}\nBHEL,X1,GATE VALVE DN150 CS CL150\n")
        assert len(rows) == 1
        assert rows[0].legacy_code == "X1"

    def test_unrecognised_commodity_is_dropped_for_inference(self):
        rows = parse(
            "cpse_org,legacy_code,description,commodity_type\n"
            "BHEL,X1,GATE VALVE DN150,not_a_commodity\n"
        )
        assert rows[0].commodity_type is None


class TestValidation:
    def test_empty_file_is_rejected(self):
        with pytest.raises(IngestValidationError):
            parse_tabular(b"", "empty.csv")

    def test_header_only_file_is_rejected(self):
        with pytest.raises(IngestValidationError) as e:
            parse("cpse_org,legacy_code,description\n")
        assert "no data" in str(e.value).lower()

    def test_missing_required_column_names_what_is_missing(self):
        with pytest.raises(IngestValidationError) as e:
            parse("cpse_org,legacy_code\nBHEL,X1\n")
        msg = str(e.value)
        assert "description" in msg
        assert "Missing required column" in msg

    def test_blank_required_values_are_rejected(self):
        with pytest.raises(IngestValidationError):
            parse("cpse_org,legacy_code,description\n,,\n")

    def test_rows_with_blanks_are_skipped_but_valid_rows_survive(self):
        rows = parse(
            "cpse_org,legacy_code,description\n"
            "BHEL,X1,GATE VALVE DN150 CS CL150\n"
            ",,\n"
            "IOCL,X2,GATE VALVE DN150 CS CL150\n"
        )
        assert [r.legacy_code for r in rows] == ["X1", "X2"]

    def test_unparseable_file_reports_the_filename(self):
        with pytest.raises(IngestValidationError) as e:
            parse_tabular(b"\x00\x01\x02binary-garbage", "broken.xlsx")
        assert "broken.xlsx" in str(e.value)

    def test_malformed_numeric_fields_degrade_to_none(self):
        rows = parse(
            "cpse_org,legacy_code,description,quantity,unit_value_inr\n"
            "BHEL,X1,GATE VALVE DN150,not-a-number,also-not\n"
        )
        assert rows[0].quantity is None
        assert rows[0].unit_value_inr is None

    def test_duplicate_rows_are_returned_and_deduplicated_later(self):
        # parse_tabular preserves duplicates; ingest_rows resolves them so the
        # report can tell the user exactly what was skipped.
        rows = parse(
            "cpse_org,legacy_code,description\n"
            "BHEL,X1,GATE VALVE DN150 CS CL150\n"
            "BHEL,X1,GATE VALVE DN150 CS CL150\n"
        )
        assert len(rows) == 2

    def test_quoted_commas_inside_a_description(self):
        rows = parse(
            'cpse_org,legacy_code,description\n'
            'BHEL,X1,"VALVE, GATE, 6 IN, CS, CL150"\n'
        )
        assert rows[0].description == "VALVE, GATE, 6 IN, CS, CL150"
