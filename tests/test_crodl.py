import unittest
from crodl import CroDL


class TestIsDomainSupported(unittest.TestCase):
    def setUp(self):
        self.dl = CroDL()

    def test_supported_domain(self):
        url = "https://www.mujrozhlas.cz"
        self.assertTrue(self.dl.is_domain_supported(url))

    def test_unsupported_domain(self):
        url = "https://vltava.rozhlas.cz"
        self.assertFalse(self.dl.is_domain_supported(url))

    def test_empty_url(self):
        url = ""
        self.assertFalse(self.dl.is_domain_supported(url))

    def test_invalid_url(self):
        url = " invalid url "
        self.assertFalse(self.dl.is_domain_supported(url))


if __name__ == "__main__":
    unittest.main()
