"""Tests for the OPCOM PZU scraper (no network required)."""

import sys
import tempfile
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from battery_rl.data.opcom import (  # noqa: E402
    ParseError,
    expected_intervals,
    export_url,
    local_midnight_utc,
    parse_day_csv,
)


class DstTests(unittest.TestCase):
    def test_interval_counts(self) -> None:
        self.assertEqual(expected_intervals(date(2026, 3, 29)), 92)  # spring forward
        self.assertEqual(expected_intervals(date(2026, 10, 25)), 100)  # fall back
        self.assertEqual(expected_intervals(date(2026, 11, 5)), 96)
        self.assertEqual(expected_intervals(date(2026, 1, 15)), 96)

    def test_local_midnight_utc(self) -> None:
        self.assertEqual(
            local_midnight_utc(date(2026, 3, 29)),
            datetime(2026, 3, 28, 22, 0, tzinfo=UTC),
        )
        self.assertEqual(
            local_midnight_utc(date(2026, 10, 25)),
            datetime(2026, 10, 24, 21, 0, tzinfo=UTC),
        )
        self.assertEqual(
            local_midnight_utc(date(2026, 7, 1)),
            datetime(2026, 6, 30, 21, 0, tzinfo=UTC),
        )
        self.assertEqual(
            local_midnight_utc(date(2026, 1, 15)),
            datetime(2026, 1, 14, 22, 0, tzinfo=UTC),
        )

    def test_last_interval_ends_at_next_midnight(self) -> None:
        for d in (date(2026, 3, 29), date(2026, 10, 25), date(2026, 11, 5)):
            count = expected_intervals(d)
            end = local_midnight_utc(d) + timedelta(minutes=15 * count)
            self.assertEqual(end, local_midnight_utc(d + timedelta(days=1)))


class UrlTests(unittest.TestCase):
    def test_export_url(self) -> None:
        self.assertEqual(
            export_url(date(2026, 1, 5)),
            "https://www.opcom.ro/rapoarte-pzu-raportPIP-export-csv/"
            "05/01/2026/ro?resolution=15",
        )


def _write_sample(path: Path, delivery_date: date, intervals: int) -> None:
    lines = [
        f'"PIP si volum tranzactionat pentru ziua de livrare: '
        f'{delivery_date:%d/%m/%Y}"',
        "",
        '"","Pret mediu [lei/MWh]","Volum [MWh]","Rezolutie"',
        '"ROPEX_DAM_Base (1-24)","1000.00","1.0","PT15M"',
        "",
        '"Zona de tranzactionare","Interval","Pret de Inchidere a Pietei [lei/MWh]",'
        '"Volum Tranzactionat [MW]","Volum Tranzactionat pe cumparare [MW]",'
        '"Volum Tranzactionat pe vanzare [MW]","Rezolutie"',
    ]
    for interval in range(1, intervals + 1):
        lines.append(
            f'"Romania","{interval}","{100 + interval:.2f}","10.0","8.0","9.0","PT15M"'
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


class ParseTests(unittest.TestCase):
    def test_parse_normal_day(self) -> None:
        delivery = date(2026, 11, 5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "day.csv"
            _write_sample(path, delivery, 96)
            parsed = parse_day_csv(path, delivery)

        self.assertEqual(parsed.intervals, 96)
        self.assertEqual(len(parsed.rows), 96)
        self.assertEqual(parsed.rows[0].interval, 1)
        self.assertEqual(parsed.rows[0].timestamp_utc, datetime(2026, 11, 4, 22, 0, tzinfo=UTC))
        self.assertAlmostEqual(parsed.rows[0].price_ron_mwh, 101.0)
        self.assertEqual(parsed.rows[-1].interval, 96)
        self.assertEqual(
            parsed.rows[-1].timestamp_utc, datetime(2026, 11, 5, 21, 45, tzinfo=UTC)
        )

    def test_wrong_interval_count_is_rejected(self) -> None:
        delivery = date(2026, 11, 5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "day.csv"
            _write_sample(path, delivery, 95)
            with self.assertRaises(ParseError):
                parse_day_csv(path, delivery)


if __name__ == "__main__":
    unittest.main()
