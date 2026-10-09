"""How the pages write things down: dates, counts, media URLs."""

import unittest

from crodl.server.format import (
    added_line,
    changed_line,
    check_report,
    curated_report,
    czech_count,
    czech_datetime,
    expired_parts_label,
    media_url,
    new_parts_label,
    parts_label,
    records_label,
    refresh_report,
    tags_report,
    upcoming_parts_label,
)
from crodl.settings import DOWNLOAD_PATH


class TestCzechDatetime(unittest.TestCase):
    def test_it_is_written_the_way_a_czech_sentence_writes_it(self):
        self.assertEqual(
            czech_datetime("2026-10-08T15:36:28"), "8. října, 2026 v 15:36"
        )

    def test_every_month_has_its_own_name(self):
        months = [
            czech_datetime(f"2026-{month:02d}-01T08:00:00") for month in range(1, 13)
        ]

        self.assertEqual(months[0], "1. ledna, 2026 v 08:00")
        self.assertEqual(months[11], "1. prosince, 2026 v 08:00")
        self.assertEqual(len(set(months)), 12)


class TestAddedLine(unittest.TestCase):
    job = {"started_at": "2026-10-08T15:36:28", "finished_at": None}

    def test_a_running_download_says_when_it_was_added(self):
        self.assertEqual(added_line(self.job), "Přidáno 8. října, 2026 v 15:36")

    def test_a_finished_download_says_when_it_finished(self):
        job = dict(self.job, finished_at="2026-10-08T15:41:02")

        self.assertEqual(
            added_line(job),
            "Přidáno 8. října, 2026 v 15:36 · dokončeno 8. října, 2026 v 15:41",
        )

    def test_finishing_within_the_same_minute_is_not_repeated(self):
        job = dict(self.job, finished_at="2026-10-08T15:36:36")

        self.assertEqual(added_line(job), "Přidáno 8. října, 2026 v 15:36")


class TestCzechCounting(unittest.TestCase):
    def test_parts(self):
        self.assertEqual(parts_label(1), "1 díl")
        self.assertEqual(parts_label(3), "3 díly")
        self.assertEqual(parts_label(14), "14 dílů")

    def test_deleted_records(self):
        self.assertEqual(records_label(1), "1 záznam")
        self.assertEqual(records_label(2), "2 záznamy")
        self.assertEqual(records_label(0), "0 záznamů")

    def test_the_helper_takes_the_three_forms(self):
        self.assertEqual(czech_count(1, "údaj", "údaje", "údajů"), "1 údaj")
        self.assertEqual(czech_count(4, "údaj", "údaje", "údajů"), "4 údaje")
        self.assertEqual(czech_count(9, "údaj", "údaje", "údajů"), "9 údajů")


class TestChangedLine(unittest.TestCase):
    def test_what_a_refresh_filled_in(self):
        self.assertEqual(changed_line(2, 1), "Doplněno z API: 2 údaje, 1 obrázek.")
        self.assertEqual(changed_line(0, 1), "Doplněno z API: 1 obrázek.")

    def test_nothing_was_missing(self):
        self.assertIn("Nic k doplnění", changed_line(0, 0))


class TestRefreshReport(unittest.TestCase):
    """The note the detail page shows after "Aktualizovat data"."""

    def test_what_was_filled_in(self):
        self.assertEqual(refresh_report("2-1"), "Doplněno z API: 2 údaje, 1 obrázek.")
        self.assertEqual(
            refresh_report("0-0"), "Nic k doplnění - údaje i obrázek už knihovna má."
        )

    def test_a_record_the_api_has_never_heard_of(self):
        report = refresh_report("none")

        self.assertIsNotNone(report)
        self.assertIn("nemá v API protějšek", report or "")

    def test_anything_else_says_nothing(self):
        self.assertIsNone(refresh_report(""))
        self.assertIsNone(refresh_report("nonsense"))


class TestCuratedReport(unittest.TestCase):
    def test_it_says_what_saving_a_work_did(self):
        self.assertEqual(curated_report("3"), "Uloženo a tagy přepsány v 3 souborech.")
        self.assertEqual(curated_report("0"), "Uloženo.")
        self.assertIsNone(curated_report(""))


class TestTagsReport(unittest.TestCase):
    def test_it_says_how_many_files_took_the_tags(self):
        self.assertEqual(tags_report("1"), "Tagy zapsány do 1 souboru.")
        self.assertEqual(tags_report("2"), "Tagy zapsány do 2 souborů.")

    def test_a_failed_write_is_said_plainly(self):
        self.assertIn("nepodařilo", tags_report("0") or "")
        self.assertIsNone(tags_report(""))


class TestCheckReport(unittest.TestCase):
    """The note the library shows after "Zkontrolovat nové díly"."""

    def test_something_new(self):
        self.assertEqual(check_report("2"), "Zkontrolováno: u 2 děl jsou nové díly.")
        self.assertEqual(check_report("1"), "Zkontrolováno: u 1 díla jsou nové díly.")

    def test_nothing_new(self):
        self.assertEqual(check_report("0"), "Zkontrolováno: zatím nic nového.")

    def test_without_a_check_nothing_is_said(self):
        self.assertIsNone(check_report(""))
        self.assertIsNone(check_report("nonsense"))


class TestNewPartsLabel(unittest.TestCase):
    def test_czech_plurals(self):
        self.assertEqual(new_parts_label(1), "1 nový díl")
        self.assertEqual(new_parts_label(3), "3 nové díly")
        self.assertEqual(new_parts_label(14), "14 nových dílů")

    def test_parts_the_radio_has_not_aired_yet(self):
        self.assertEqual(upcoming_parts_label(1), "Ještě 1 díl")
        self.assertEqual(upcoming_parts_label(2), "Ještě 2 díly")
        self.assertEqual(upcoming_parts_label(9), "Ještě 9 dílů")

    def test_parts_whose_streams_are_gone(self):
        self.assertEqual(expired_parts_label(1), "1 díl nedostupný")
        self.assertEqual(expired_parts_label(2), "2 díly nedostupné")
        self.assertEqual(expired_parts_label(7), "7 dílů nedostupných")


class TestMediaUrl(unittest.TestCase):
    def test_a_file_in_the_library_gets_a_url(self):
        path = str(DOWNLOAD_PATH / "Seriály" / "Bohumil Hrabal" / "8 - Díl.mp3")

        self.assertEqual(
            media_url(path),
            "/library/Seri%C3%A1ly/Bohumil%20Hrabal/8%20-%20D%C3%ADl.mp3",
        )

    def test_nothing_to_serve(self):
        self.assertIsNone(media_url(None))
        self.assertIsNone(media_url(""))

    def test_a_file_outside_the_download_directory_has_no_url(self):
        # The media route would refuse it, so the page must not link to it.
        self.assertIsNone(media_url("/etc/passwd"))
        self.assertIsNone(media_url(str(DOWNLOAD_PATH / ".." / "outside.mp3")))


if __name__ == "__main__":
    unittest.main()
