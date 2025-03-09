import unittest
from unittest.mock import patch, Mock
from requests import Session

from crodl.tools.scrap import (
    AudioUUIDDoesNotExist,
    PageDoesNotExist,
    DataEntryDoesNotExist,
    PlayerWrapperDoesNotExist,
    ShowUUIDDoesNotExist,
    get_attributes,
    get_audio_link_of_preferred_format,
    get_audio_uuid,
    get_js_value_from_url,
    get_series_id,
    get_show_uuid,
    is_series,
    is_show,
)


class TestGetAudioUUID(unittest.TestCase):
    @patch.object(Session, "get")
    def test_successful_retrieval(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            '<section class="player-wrapper" data-entry=\'{"uuid": "12345"}\'>'
        )
        mock_get.return_value = mock_response

        uuid = get_audio_uuid(site_url, Session())
        self.assertEqual(uuid, "12345")

    @patch.object(Session, "get")
    def test_handle_404(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with self.assertRaises(PageDoesNotExist):
            get_audio_uuid(site_url, Session())

    @patch.object(Session, "get")
    def test_handle_player_wrapper_not_found(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<div></div>"
        mock_get.return_value = mock_response

        with self.assertRaises(PlayerWrapperDoesNotExist):
            get_audio_uuid(site_url, Session())

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
            get_audio_uuid(site_url, Session())

    @patch.object(Session, "get")
    def test_data_entry_not_found(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<section class="player-wrapper">'
        mock_get.return_value = mock_response
        with self.assertRaises(DataEntryDoesNotExist):
            get_audio_uuid(site_url, Session())

    @patch.object(Session, "get")
    def test_data_entry_is_empty_string(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<section class="player-wrapper" data-entry="">'
        mock_get.return_value = mock_response
        with self.assertRaises(DataEntryDoesNotExist):
            get_audio_uuid(site_url, Session())


class TestGetShowUUID(unittest.TestCase):
    @patch.object(Session, "get")
    def test_successful_retrieval(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = (
            '<div class="b-detail" data-entry=\'{"show-uuid": "12345"}\'></div>'
        )
        mock_get.return_value = mock_response

        uuid = get_show_uuid(site_url, Session())
        self.assertEqual(uuid, "12345")

    @patch.object(Session, "get")
    def test_handle_404(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with self.assertRaises(PageDoesNotExist):
            get_show_uuid(site_url, Session())

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
            get_show_uuid(site_url, Session())

    @patch.object(Session, "get")
    def test_data_entry_not_found(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<div class="b-detail"></div>'
        mock_get.return_value = mock_response
        with self.assertRaises(DataEntryDoesNotExist):
            get_show_uuid(site_url, Session())

    @patch.object(Session, "get")
    def test_data_entry_is_empty_string(self, mock_get):
        site_url = "https://example.com"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '<div class="b-detail" data-entry=""></div>'
        mock_get.return_value = mock_response
        with self.assertRaises(DataEntryDoesNotExist):
            get_show_uuid(site_url, Session())


class TestGetAttributes(unittest.TestCase):
    @patch.object(Session, "get")
    def test_successful_retrieval(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"attributes": "test_attributes"}}
        mock_get.return_value = mock_response

        attributes = get_attributes("12345", Session())
        self.assertEqual(attributes, "test_attributes")

    @patch.object(Session, "get")
    def test_handle_response_without_data(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        with self.assertRaises(AttributeError):
            get_attributes("12345", Session())

    @patch.object(Session, "get")
    def test_handle_missing_attributes_key(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {"data": {}}
        mock_get.return_value = mock_response

        result = get_attributes("12345", Session())
        self.assertEqual(result, {})


class TestGetAudioLinkOfPreferredFormat(unittest.TestCase):
    @patch("crodl.tools.scrap.get_preferred_audio_format")
    def test_preferred_format_found(self, mock_get_preferred_audio_format):
        attrs = {
            "audioLinks": [
                {"variant": "mp3", "url": "audio1.mp3"},
                {"variant": "aac", "url": "audio2.aac"},
            ]
        }
        mock_format = mock_get_preferred_audio_format.return_value
        mock_format.value = "aac"
        result = get_audio_link_of_preferred_format(attrs)
        self.assertEqual(result, "audio1.mp3")

    @patch("crodl.tools.scrap.get_preferred_audio_format")
    def test_no_audio_links(self, mock_get_preferred_audio_format):
        attrs = {"audioLinks": []}
        mock_format = mock_get_preferred_audio_format.return_value
        mock_format.value = "aac"
        result = get_audio_link_of_preferred_format(attrs)
        self.assertEqual(result, None)

    @patch("crodl.tools.scrap.get_preferred_audio_format")
    def test_preferred_format_not_found(self, mock_get_preferred_audio_format):
        attrs = {
            "audioLinks": [
                {"variant": "wma", "url": "audio1.wma"},
                {"variant": "ogg", "url": "audio2.ogg"},
            ]
        }
        mock_format = mock_get_preferred_audio_format.return_value
        mock_format.value = "aac"
        result = get_audio_link_of_preferred_format(attrs)
        self.assertIsNone(result)


class TestGetJsValueFromUrl(unittest.TestCase):
    @patch.object(Session, "get")
    def test_get_js_value_from_url_success(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.text = '<script>var dl = {"siteEntityBundle":"serial", "contentId":"1234"};</script>'
        mock_get.return_value = response

        result = get_js_value_from_url("http://example.com", "contentId", Session())
        self.assertEqual(result, "1234")

    @patch.object(Session, "get")
    def test_get_js_value_from_url_failure(self, mock_get):
        response = Mock()
        response.status_code = 404
        mock_get.return_value = response

        result = get_js_value_from_url("http://example.com", "jsvar", Session())
        self.assertIsNone(result)

    @patch.object(Session, "get")
    def test_get_js_value_from_url_failure_no_match(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.text = '<script>var dl = {"contentId":};</script>'
        mock_get.return_value = response

        result = get_js_value_from_url("http://example.com", "conte", Session())
        self.assertIsNone(result)

    @patch.object(Session, "get")
    def test_get_js_value_from_url_failure_jsvar_not_in_text(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.text = '<script>var dl = {"siteEntityBundle":"serial", "contentId":"1234"};</script>'
        mock_get.return_value = response

        result = get_js_value_from_url("http://example.com", "jsvar", Session())
        self.assertIsNone(result)


class TestIsSerial(unittest.TestCase):
    @patch("crodl.tools.scrap.get_js_value_from_url")
    def test_is_serial_true(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "serial"
        result = is_series("http://example.com", Session())
        self.assertTrue(result)

    @patch("crodl.tools.scrap.get_js_value_from_url")
    def test_is_serial_false(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "movie"
        result = is_series("http://example.com", Session())
        self.assertFalse(result)


class TestGetSeriesId(unittest.TestCase):
    @patch("crodl.tools.scrap.get_js_value_from_url")
    def test_valid_series_id(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "31415"
        result = get_series_id("http://example.com", Session())
        self.assertEqual(result, "31415")


class TestIsShow(unittest.TestCase):
    @patch("crodl.tools.scrap.get_js_value_from_url")
    def test_is_show_true(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "show"
        result = is_show("http://example.com", Session())
        self.assertTrue(result)

    @patch("crodl.tools.scrap.get_js_value_from_url")
    def test_is_show_false(self, mock_get_js_value_from_url):
        mock_get_js_value_from_url.return_value = "serial"
        result = is_show("http://example.com", Session())
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
