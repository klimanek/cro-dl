import logging
import unittest

from uvicorn.logging import AccessFormatter

from crodl.server.access_log import PercentDecodedAccessLog, log_readable_paths


def access_record(path: str, status: int = 200) -> logging.LogRecord:
    """A record shaped exactly like the one uvicorn logs for a request."""
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:61787", "GET", path, "1.1", status),
        exc_info=None,
    )


class TestPercentDecodedAccessLog(unittest.TestCase):
    """The terminal must show Czech paths, not `%C3%A1` soup."""

    formatter = AccessFormatter(
        '%(client_addr)s - "%(request_line)s" %(status_code)s', use_colors=False
    )

    def render(self, path: str) -> str:
        record = access_record(path)
        PercentDecodedAccessLog().filter(record)
        return self.formatter.format(record)

    def test_a_czech_path_is_decoded(self):
        # The URL from the reported terminal output.
        path = "/library/Seri%C3%A1ly/Bohumil%20Hrabal%20-%20Obsluhoval%20jsem%20anglick%C3%A9ho%20kr%C3%A1le/5%20-%20Bohumil%20Hrabal%20-%20Obsluhoval%20jsem%20anglick%C3%A9ho%20kr%C3%A1le.aac"

        line = self.render(path)

        self.assertIn(
            "/library/Seriály/Bohumil Hrabal - Obsluhoval jsem anglického krále/"
            "5 - Bohumil Hrabal - Obsluhoval jsem anglického krále.aac",
            line,
        )
        self.assertNotIn("%C3%A1", line)

    def test_the_rest_of_the_line_is_untouched(self):
        self.assertEqual(self.render("/"), '127.0.0.1:61787 - "GET / HTTP/1.1" 200 OK')

    def test_a_query_string_is_decoded_too(self):
        self.assertIn("/search?q=čapek", self.render("/search?q=%C4%8Dapek"))


class TestPercentDecodedAccessLogFilter(unittest.TestCase):
    def test_a_record_from_another_logger_passes_through(self):
        record = logging.LogRecord(
            "uvicorn.error", logging.INFO, __file__, 1, "hello %s", ("world",), None
        )

        self.assertTrue(PercentDecodedAccessLog().filter(record))
        self.assertEqual(record.args, ("world",))

    def test_a_record_without_arguments_passes_through(self):
        record = logging.LogRecord(
            "uvicorn.access", logging.INFO, __file__, 1, "no arguments", None, None
        )

        self.assertTrue(PercentDecodedAccessLog().filter(record))
        self.assertIsNone(record.args)

    def test_installing_it_twice_adds_one_filter(self):
        logger = logging.getLogger("crodl.test.access")

        log_readable_paths(logger.name)
        log_readable_paths(logger.name)

        self.assertEqual(len(logger.filters), 1)
        self.assertIsInstance(logger.filters[0], PercentDecodedAccessLog)


class TestLogFileEncoding(unittest.TestCase):
    def test_the_log_file_is_written_as_utf8(self):
        # Czech titles go into this file; the locale codec (cp1250 on Windows)
        # would mangle them.
        from crodl.tools.logger import logfile

        self.assertEqual(logfile.encoding, "utf-8")


if __name__ == "__main__":
    unittest.main()
