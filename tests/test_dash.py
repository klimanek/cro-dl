import tempfile

import shutil
from pathlib import Path

import unittest
from unittest.mock import patch, PropertyMock, Mock

from bs4 import BeautifulSoup
from crodl.streams.dash import (
    DASH,
    get_m4s_segment_url,
    audio_segment_times,
    segments_info,
    segments_urls,
)

from crodl.settings import TIMEOUT


class TestGetM4sSegmentUrl(unittest.TestCase):
    def test_init_segment_url(self):
        audio_link = "https://example.com/audio.mp4/manifest.mpd"
        repr_id = "p0aa0br193031"
        segment_time = None
        init = True
        expected_url = "https://example.com/audio.mp4/segment_ctaudio_ridp0aa0br193031_cinit_mpd.m4s"
        self.assertEqual(
            get_m4s_segment_url(audio_link, repr_id, segment_time, init), expected_url
        )

    def test_non_init_segment_url_integer(self):
        audio_link = "https://example.com/audio.mp4/manifest.mpd"
        repr_id = "p0aa0br193031"
        segment_time = 10
        init = False
        expected_url = "https://example.com/audio.mp4/segment_ctaudio_ridp0aa0br193031_cs10_mpd.m4s"
        self.assertEqual(
            get_m4s_segment_url(audio_link, repr_id, segment_time, init), expected_url
        )

    def test_non_init_segment_url_string(self):
        audio_link = "https://example.com/audio.mp4/manifest.mpd"
        repr_id = "p0aa0br193031"
        segment_time = "20"
        init = False
        expected_url = "https://example.com/audio.mp4/segment_ctaudio_ridp0aa0br193031_cs20_mpd.m4s"
        self.assertEqual(
            get_m4s_segment_url(audio_link, repr_id, segment_time, init), expected_url
        )


class TestAudioSegmentTimes(unittest.TestCase):
    def test_no_s_tags(self):
        mpd_content = BeautifulSoup("<MPD></MPD>", "xml")
        segment_times = audio_segment_times(mpd_content)
        self.assertEqual(segment_times, [])  # Expect an empty list

    def test_multiple_s_tags(self):
        mpd_content = BeautifulSoup(
            '<MPD><S d="3" r="1"/><S d="5" r="2"/></MPD>', "xml"
        )
        segment_times = audio_segment_times(mpd_content)
        self.assertEqual(
            segment_times,
            [3, 3, 5, 5, 5],
        )  # Expect [3, 3, 5, 5, 5]

    def test_missing_r_attribute(self):
        mpd_content = BeautifulSoup('<MPD><S d="2"/><S d="4" r="3"/></MPD>', "xml")
        segment_times = audio_segment_times(mpd_content)
        self.assertEqual(segment_times, [2, 4, 4, 4, 4])  # Expect [2, 4, 4, 4, 4]


@patch("crodl.streams.dash.audio_segment_times")
class TestSegmentsInfo(unittest.TestCase):
    def test_representation_found(self, mock_audio_segment_times):
        manifest_content = '<MPD><Representation id="123"></Representation></MPD>'
        mock_audio_segment_times.return_value = [10, 20, 30]
        expected_result = ([10, 30, 60], "123")
        self.assertEqual(segments_info(manifest_content), expected_result)

    def test_representation_not_found(self, mock_audio_segment_times):
        manifest_content = "<MPD></MPD>"
        mock_audio_segment_times.return_value = []
        with self.assertRaises(KeyError):
            segments_info(manifest_content)


class TestSegmentsUrls(unittest.TestCase):
    @patch("crodl.streams.dash.get_m4s_segment_url")  # Correct the patch target
    @patch.object(DASH, "content", new_callable=PropertyMock)
    def test_segments_urls(self, mock_content, mock_get_m4s_segment_url):
        manifest_content = """
        <MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT10M">
            <Period>
                <AdaptationSet>
                    <SegmentTemplate timescale="1000" initialization="init.m4s">
                        <SegmentTimeline>
                            <S d="480240"/>
                            <S d="960528"/>
                            <S d="1920000"/>
                        </SegmentTimeline>
                    </SegmentTemplate>
                    <Representation id="09876abc" codecs="mp4a.40.2" audioSamplingRate="48000" bandwidth="128005">
                    </Representation>
                </AdaptationSet>
            </Period>
        </MPD>
        """
        mock_content.return_value = manifest_content

        def mock_get_url(audio_link, repr_id, segment_time=None, init=False):
            assert audio_link
            if init:
                return (
                    f"https://example.com/stream/xyz.m4a/audio_{repr_id}_cinit_mpd.m4s"
                )
            return f"https://example.com/stream/xyz.m4a/audio_{repr_id}_cs{segment_time}_mpd.m4s"

        mock_get_m4s_segment_url.side_effect = mock_get_url

        manifest_mock = Mock(spec=DASH)
        manifest_mock.url = "https://example.com/stream/xyz.m4a/manifest.mpd"
        manifest_mock.segments_path = "/some/path"

        manifest_mock.content = mock_content.return_value

        result = segments_urls(manifest_mock)

        expected_urls = [
            "https://example.com/stream/xyz.m4a/audio_09876abc_cinit_mpd.m4s",  # initial segment
            "https://example.com/stream/xyz.m4a/audio_09876abc_cs0_mpd.m4s",  # zeroth segment
            "https://example.com/stream/xyz.m4a/audio_09876abc_cs480240_mpd.m4s",  # first segment
            "https://example.com/stream/xyz.m4a/audio_09876abc_cs1440768_mpd.m4s",
        ]

        self.assertEqual(result, expected_urls)


class TestManifest(unittest.TestCase):
    @patch("crodl.streams.utils.get_m4a_url")
    @patch("crodl.tools.scrap.cro_session.get")
    def test_get_manifest(self, mock_get, mock_get_m4a_url):
        # Test case: fetching manifest and saving it locally
        mock_get_m4a_url.return_value = "https://example.com/test.mp4"
        mock_get.return_value.content = b'{"manifest": "test"}'

        manifest = DASH("https://example.com/test.mp4/manifest.mpd", "Some Title")
        manifest._get_manifest()  # pylint: disable=protected-access

        mock_get.assert_called_once_with(
            "https://example.com/test.mp4/manifest.mpd", timeout=TIMEOUT
        )
        with open(f"{manifest.segments_path}/manifest.mpd", "rb") as f:
            content = f.read()
        self.assertEqual(content, b'{"manifest": "test"}')


class TestManifestContent(unittest.TestCase):
    def test_content_exists(self):
        # Create a mock manifest file
        segments_path = Path(tempfile.mkdtemp())
        manifest_file = segments_path / "manifest.mpd"

        with open(manifest_file, "w", encoding="utf-8") as f:
            f.write("Mock manifest content")

        # Initialize Manifest with a mock URL
        url = "http://example.com/mp4/manifest.mpd"
        manifest = DASH(url, "Some Title")
        manifest.segments_path = segments_path

        # Test that the content property returns the manifest content
        self.assertEqual(manifest.content, "Mock manifest content")
        shutil.rmtree(segments_path)


@patch("crodl.streams.dash.segments_info")
class TestManifestIdProperty(unittest.TestCase):
    def setUp(self):
        self.manifest = DASH("http://example.com/mp4/manifest.mpd", "Some Title")

    def test_id_property_returns_correct_value(self, mock_segments_info):
        mock_segments_info.return_value = (None, "12345")
        self.assertEqual(self.manifest.id, "12345")

    def test_id_property_raises_exception_on_invalid_value(self, mock_segments_info):
        mock_segments_info.return_value = (None, None)
        with self.assertRaises(ValueError):
            self.manifest.id


class TestSegmentUrls(unittest.TestCase):
    def setUp(self):
        self.manifest = DASH("http://example.com/mp4/manifest.mpd", "Some Title")

    def test_segment_urls_returns_list_of_strings(self):
        with patch("crodl.streams.dash.segments_urls") as mock_segments_urls:
            mock_segments_urls.return_value = ["url1", "url2"]
            segment_urls = self.manifest.segment_urls
            self.assertIsInstance(segment_urls, list)
            self.assertEqual(len(segment_urls), 2)
            self.assertEqual(segment_urls[0], "url1")
            self.assertEqual(segment_urls[1], "url2")

    def test_segment_urls_calls_segments_urls(self):
        with patch("crodl.streams.dash.segments_urls") as mock_segments_urls:
            self.manifest.segment_urls
            mock_segments_urls.assert_called_once_with(self.manifest)

    def test_segment_urls_returns_empty_list(self):
        with patch("crodl.streams.dash.segments_urls") as mock_segments_urls:
            mock_segments_urls.return_value = []
            segment_urls = self.manifest.segment_urls
            self.assertEqual(segment_urls, [])

    def test_segment_urls_raises_exception(self):
        with patch("crodl.streams.dash.segments_urls") as mock_segments_urls:
            mock_segments_urls.side_effect = Exception("Test exception")
            with self.assertRaises(Exception):
                self.manifest.segment_urls


@patch("os.listdir")
class TestManifestCreateListTxt(unittest.TestCase):
    def setUp(self):
        self.manifest = DASH("http://example.com/mp4/manifest.mpd", "Some Title")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.manifest.segments_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch.object(DASH, "id", new_callable=PropertyMock)
    def test_no_segment_files(self, mock_listdir, mock_id):
        mock_id.return_value = "abc123"
        mock_listdir.return_value = []
        with self.assertRaises(ValueError):
            self.manifest.create_list_txt()

    @patch("crodl.streams.utils.simplify_audio_name")
    @patch("crodl.streams.utils.audio_segment_sort")
    @patch.object(DASH, "id", new_callable=PropertyMock)
    def test_create_list_txt(
        self, mock_id, mock_audio_segment_sort, mock_simplify_audio_name, mock_listdir
    ):
        mock_id.return_value = "abc123"
        mock_listdir.return_value = [
            "cinit.m4s",
            "segment_1.m4s",
            "segment_2.m4s",
            "segment_3.m4s",
        ]
        mock_simplify_audio_name.side_effect = [
            "cinit.m4s",
            "segment_1.m4s",
            "segment_2.m4s",
            "segment_3.m4s",
        ]
        mock_audio_segment_sort.return_value = 1

        self.manifest.create_list_txt()

        with open(
            f"{self.manifest.segments_path}/list.txt", "r", encoding="utf-8"
        ) as f:
            contents = f.read()
            self.assertEqual(
                contents, "cinit.m4s\nsegment_1.m4s\nsegment_2.m4s\nsegment_3.m4s\n"
            )


if __name__ == "__main__":
    unittest.main()
