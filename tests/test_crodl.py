import unittest
from crodl.main import is_domain_supported


class TestIsDomainSupported(unittest.TestCase):
    def test_supported_domain(self):
        url = "https://www.mujrozhlas.cz"
        self.assertTrue(is_domain_supported(url))

    def test_unsupported_domain(self):
        url = "https://vltava.rozhlas.cz"
        self.assertFalse(is_domain_supported(url))

    def test_empty_url(self):
        url = ""
        with self.assertRaises(ValueError):
            is_domain_supported(url)

    def test_invalid_url(self):
        url = " invalid url "
        with self.assertRaises(ValueError):
            is_domain_supported(url)


if __name__ == "__main__":
    unittest.main()
