import unittest
from unittest.mock import Mock, patch
from requests import Session

from crodl.exceptions import (
    AudioUUIDDoesNotExist,
    DataEntryDoesNotExist,
    PageDoesNotExist,
    PlayerWrapperDoesNotExist,
    ShowUUIDDoesNotExist,
)
from crodl.settings import API_SERVER
from crodl.tools.api_client import CroAPIClient


class TestGetAudioUUID(unittest.TestCase):
    def setUp(self):
        self.client = CroAPIClient(session=Session())

    @patch.object(Session, "get")
    def test_successful_retrieval(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            '<section class="player-wrapper" data-entry=\'{"uuid": "12345"}\'>'
        )
        mock_get.return_value = mock_response

        uuid = self.client.get_audio_uuid(site_url)
        self.assertEqual(uuid, "12345")

    @patch.object(Session, "get")
    def test_handle_404(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with self.assertRaises(PageDoesNotExist):
            self.client.get_audio_uuid(site_url)

    @patch.object(Session, "get")
    def test_handle_player_wrapper_not_found(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<div></div>"
        mock_get.return_value = mock_response

        with self.assertRaises(PlayerWrapperDoesNotExist):
            self.client.get_audio_uuid(site_url)

    @patch.object(Session, "get")
    def test_handle_uuid_not_found(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            '<section class="player-wrapper" data-entry=\'{"invalid_key": "12345"}\'>'
        )
        mock_get.return_value = mock_response

        with self.assertRaises(AudioUUIDDoesNotExist):
            self.client.get_audio_uuid(site_url)

    @patch.object(Session, "get")
    def test_data_entry_not_found(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<section class="player-wrapper">'
        mock_get.return_value = mock_response
        with self.assertRaises(DataEntryDoesNotExist):
            self.client.get_audio_uuid(site_url)

    @patch.object(Session, "get")
    def test_data_entry_is_empty_string(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<section class="player-wrapper" data-entry="">'
        mock_get.return_value = mock_response
        with self.assertRaises(DataEntryDoesNotExist):
            self.client.get_audio_uuid(site_url)


class TestGetShowUUID(unittest.TestCase):
    def setUp(self):
        self.client = CroAPIClient(session=Session())

    @patch.object(Session, "get")
    def test_successful_retrieval(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            '<div class="b-detail" data-entry=\'{"show-uuid": "12345"}\'></div>'
        )
        mock_get.return_value = mock_response

        uuid = self.client.get_show_uuid(site_url)
        self.assertEqual(uuid, "12345")

    @patch.object(Session, "get")
    def test_handle_404(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with self.assertRaises(PageDoesNotExist):
            self.client.get_show_uuid(site_url)

    @patch.object(Session, "get")
    def test_handle_uuid_not_found(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            '<div class="b-detail" data-entry=\'{"invalid_key": "12345"}\'></div>'
        )
        mock_get.return_value = mock_response

        with self.assertRaises(ShowUUIDDoesNotExist):
            self.client.get_show_uuid(site_url)

    @patch.object(Session, "get")
    def test_data_entry_not_found(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<div class="b-detail"></div>'
        mock_get.return_value = mock_response
        with self.assertRaises(DataEntryDoesNotExist):
            self.client.get_show_uuid(site_url)

    @patch.object(Session, "get")
    def test_data_entry_is_empty_string(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<div class="b-detail" data-entry=""></div>'
        mock_get.return_value = mock_response
        with self.assertRaises(DataEntryDoesNotExist):
            self.client.get_show_uuid(site_url)


class TestGetEpisodeData(unittest.TestCase):
    def setUp(self):
        self.client = CroAPIClient(session=Session())

    @patch.object(Session, "get")
    def test_successful_retrieval(self, mock_get):
        payload = {"data": {"id": "12345", "attributes": {}}}
        mock_response = Mock()
        mock_response.json.return_value = payload
        mock_get.return_value = mock_response

        self.assertEqual(self.client.get_episode_data("12345"), payload)
        mock_get.assert_called_once_with(f"{API_SERVER}/episodes/12345", timeout=10)

    @patch.object(Session, "get")
    def test_empty_response_raises(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        with self.assertRaises(AttributeError):
            self.client.get_episode_data("12345")

    @patch.object(Session, "get")
    def test_response_without_data_returns_empty_dict(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"meta": {}}
        mock_get.return_value = mock_response

        self.assertEqual(self.client.get_episode_data("12345"), {})


class TestGetJsValueFromUrl(unittest.TestCase):
    def setUp(self):
        self.client = CroAPIClient(session=Session())

    @patch.object(Session, "get")
    def test_get_js_value_from_url_success(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.text = (
            '<script>var dl = {"siteEntityBundle":"serial", "contentId":"1234"};'
            "</script>"
        )
        mock_get.return_value = response

        result = self.client.get_js_value_from_url("http://example.com", "contentId")
        self.assertEqual(result, "1234")

    @patch.object(Session, "get")
    def test_get_js_value_from_url_failure(self, mock_get):
        response = Mock()
        response.status_code = 404
        mock_get.return_value = response

        result = self.client.get_js_value_from_url("http://example.com", "jsvar")
        self.assertIsNone(result)

    @patch.object(Session, "get")
    def test_get_js_value_from_url_failure_no_match(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.text = '<script>var dl = {"contentId":};</script>'
        mock_get.return_value = response

        result = self.client.get_js_value_from_url("http://example.com", "conte")
        self.assertIsNone(result)

    @patch.object(Session, "get")
    def test_get_js_value_from_url_failure_jsvar_not_in_text(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.text = (
            '<script>var dl = {"siteEntityBundle":"serial", "contentId":"1234"};'
            "</script>"
        )
        mock_get.return_value = response

        result = self.client.get_js_value_from_url("http://example.com", "jsvar")
        self.assertIsNone(result)


class TestIsSeries(unittest.TestCase):
    def setUp(self):
        self.client = CroAPIClient(session=Session())

    @patch.object(CroAPIClient, "get_js_value_from_url")
    def test_is_serial_true(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "serial"
        self.assertTrue(self.client.is_series("http://example.com"))

    @patch.object(CroAPIClient, "get_js_value_from_url")
    def test_is_serial_false(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "movie"
        self.assertFalse(self.client.is_series("http://example.com"))


class TestGetSeriesId(unittest.TestCase):
    def setUp(self):
        self.client = CroAPIClient(session=Session())

    @patch.object(CroAPIClient, "get_js_value_from_url")
    def test_valid_series_id(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "31415"
        result = self.client.get_series_id("http://example.com")
        self.assertEqual(result, "31415")


class TestIsShow(unittest.TestCase):
    def setUp(self):
        self.client = CroAPIClient(session=Session())

    @patch.object(CroAPIClient, "get_js_value_from_url")
    def test_is_show_true(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "show"
        self.assertTrue(self.client.is_show("http://example.com"))

    @patch.object(CroAPIClient, "get_js_value_from_url")
    def test_is_show_false(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "serial"
        self.assertFalse(self.client.is_show("http://example.com"))


if __name__ == "__main__":
    unittest.main()
