import pytest
from unittest.mock import MagicMock, patch


class TestParseTagData:
    def test_valid_album_tag(self):
        from nfc_interface import parse_tag_data
        assert parse_tag_data("apple:1440903625") == {"service": "apple", "type": "album", "id": "1440903625"}

    def test_valid_track_tag(self):
        from nfc_interface import parse_tag_data
        assert parse_tag_data("apple:track:1440904001") == {"service": "apple", "type": "track", "id": "1440904001"}

    def test_invalid_format_raises(self):
        from nfc_interface import parse_tag_data
        with pytest.raises(ValueError):
            parse_tag_data("notvalid")

    def test_unknown_service_parses_without_error(self):
        from nfc_interface import parse_tag_data
        result = parse_tag_data("spotify:1440903625")
        assert result == {"service": "spotify", "type": "album", "id": "1440903625"}

    def test_empty_string_raises(self):
        from nfc_interface import parse_tag_data
        with pytest.raises(ValueError):
            parse_tag_data("")

    def test_apple_with_no_id_raises(self):
        from nfc_interface import parse_tag_data
        with pytest.raises(ValueError):
            parse_tag_data("apple:")

    def test_track_with_no_id_raises(self):
        from nfc_interface import parse_tag_data
        with pytest.raises(ValueError):
            parse_tag_data("apple:track:")


class TestMockNFC:
    def test_read_tag_returns_input(self):
        from nfc_interface import MockNFC
        nfc = MockNFC()
        with patch("builtins.input", return_value="apple:1440903625"):
            result = nfc.read_tag()
        assert result == "apple:1440903625"

    def test_write_tag_returns_true(self):
        from nfc_interface import MockNFC
        nfc = MockNFC()
        assert nfc.write_tag("apple:1440903625") is True

    def test_write_url_tag_returns_true(self):
        from nfc_interface import MockNFC
        nfc = MockNFC()
        assert nfc.write_url_tag("http://10.0.0.71:5000") is True


class TestParseNdefText:
    def test_returns_none_for_empty_bytes(self):
        from nfc_interface import _parse_ndef_text
        assert _parse_ndef_text(b"") is None

    def test_returns_none_for_blank_card(self):
        from nfc_interface import _parse_ndef_text
        assert _parse_ndef_text(bytes(16)) is None  # all zeros

    def test_returns_none_for_non_ndef(self):
        from nfc_interface import _parse_ndef_text
        assert _parse_ndef_text(b"\x01\x02\x03\x04") is None

    def test_parses_text_record(self):
        from nfc_interface import _parse_ndef_text, _build_ndef_text_tlv
        tlv = _build_ndef_text_tlv("apple:1440903625")
        assert _parse_ndef_text(tlv) == "apple:1440903625"

    def test_parses_text_with_extra_trailing_bytes(self):
        from nfc_interface import _parse_ndef_text, _build_ndef_text_tlv
        tlv = _build_ndef_text_tlv("apple:track:1440904001") + bytes(8)
        assert _parse_ndef_text(tlv) == "apple:track:1440904001"

    def test_returns_none_for_short_record(self):
        from nfc_interface import _parse_ndef_text
        # TLV type=0x03, length=2, only 2 bytes of record data (too short to parse)
        assert _parse_ndef_text(bytes([0x03, 0x02, 0xD1, 0x01])) is None

    def test_returns_none_for_uri_record_type(self):
        from nfc_interface import _build_ndef_uri_tlv, _parse_ndef_text
        # URI records have type 'U' (0x55), not 'T' - should return None
        tlv = _build_ndef_uri_tlv("http://vinyl-pi.local:5000")
        assert _parse_ndef_text(tlv) is None

    def test_parses_three_byte_length_encoding(self):
        from nfc_interface import _parse_ndef_text
        # Build TLV manually with 3-byte length encoding (length byte = 0xFF)
        payload = bytes([0x02, 0x65, 0x6E]) + b"apple:1440903625"  # lang "en"
        record = bytes([0xD1, 0x01, len(payload), 0x54]) + payload
        length = len(record)
        tlv = bytes([0x03, 0xFF, (length >> 8) & 0xFF, length & 0xFF]) + record + bytes([0xFE])
        assert _parse_ndef_text(tlv) == "apple:1440903625"


class TestBuildNdefTextTlv:
    def test_starts_with_ndef_tlv_type(self):
        from nfc_interface import _build_ndef_text_tlv
        tlv = _build_ndef_text_tlv("hello")
        assert tlv[0] == 0x03

    def test_ends_with_terminator_before_padding(self):
        from nfc_interface import _build_ndef_text_tlv
        tlv = _build_ndef_text_tlv("hello")
        non_pad = tlv.rstrip(b"\x00")
        assert non_pad[-1] == 0xFE

    def test_padded_to_4_byte_boundary(self):
        from nfc_interface import _build_ndef_text_tlv
        for text in ["hi", "apple:1440903625", "apple:track:1440904001"]:
            assert len(_build_ndef_text_tlv(text)) % 4 == 0

    def test_round_trip(self):
        from nfc_interface import _build_ndef_text_tlv, _parse_ndef_text
        for text in ["apple:1440903625", "apple:track:1440904001", "hello world"]:
            assert _parse_ndef_text(_build_ndef_text_tlv(text)) == text


class TestBuildNdefUriTlv:
    def test_http_prefix_code(self):
        from nfc_interface import _build_ndef_uri_tlv
        tlv = _build_ndef_uri_tlv("http://vinyl-pi.local:5000")
        # Structure: 03 [len] D1 01 [pay_len] 55 [prefix_code] [body...]
        assert tlv[0] == 0x03   # NDEF TLV type
        assert tlv[2] == 0xD1   # record header
        assert tlv[5] == 0x55   # 'U' type byte
        assert tlv[6] == 0x03   # http:// prefix code

    def test_https_prefix_code(self):
        from nfc_interface import _build_ndef_uri_tlv
        tlv = _build_ndef_uri_tlv("https://vinyl-pi.local")
        assert tlv[6] == 0x04   # https:// prefix code

    def test_unknown_scheme_uses_no_prefix(self):
        from nfc_interface import _build_ndef_uri_tlv
        tlv = _build_ndef_uri_tlv("ftp://example.com")
        assert tlv[6] == 0x00

    def test_padded_to_4_byte_boundary(self):
        from nfc_interface import _build_ndef_uri_tlv
        assert len(_build_ndef_uri_tlv("http://vinyl-pi.local:5000")) % 4 == 0


class TestPN532NFC:
    def _make_nfc(self, mock_pn532):
        """Create PN532NFC with injected mock hardware object, bypassing Pi-only imports."""
        from nfc_interface import PN532NFC
        with patch.object(PN532NFC, "__init__", lambda self: setattr(self, "_pn532", mock_pn532)):
            return PN532NFC()

    def test_read_tag_returns_none_when_no_card(self):
        mock_pn532 = MagicMock()
        mock_pn532.read_passive_target.return_value = None
        nfc = self._make_nfc(mock_pn532)
        assert nfc.read_tag() is None

    def test_read_tag_returns_none_for_blank_card(self):
        mock_pn532 = MagicMock()
        mock_pn532.read_passive_target.return_value = b"\x04\x12\x34\x56"
        mock_pn532.ntag2xx_read_block.return_value = bytes(4)  # all zeros = blank
        nfc = self._make_nfc(mock_pn532)
        assert nfc.read_tag() is None

    def test_read_tag_parses_text_record(self):
        from nfc_interface import _build_ndef_text_tlv
        mock_pn532 = MagicMock()
        mock_pn532.read_passive_target.return_value = b"\x04\x12\x34\x56"
        tlv = _build_ndef_text_tlv("apple:1440903625")
        blocks = [tlv[i:i + 4] for i in range(0, len(tlv), 4)]
        mock_pn532.ntag2xx_read_block.side_effect = (
            lambda block: blocks[block - 4] if (block - 4) < len(blocks) else bytes(4)
        )
        nfc = self._make_nfc(mock_pn532)
        assert nfc.read_tag() == "apple:1440903625"

    def test_write_tag_writes_correct_blocks(self):
        from nfc_interface import _build_ndef_text_tlv
        mock_pn532 = MagicMock()
        mock_pn532.ntag2xx_write_block.return_value = True
        nfc = self._make_nfc(mock_pn532)
        result = nfc.write_tag("apple:1440903625")
        assert result is True
        assert mock_pn532.ntag2xx_write_block.called
        first_call = mock_pn532.ntag2xx_write_block.call_args_list[0]
        assert first_call[0][0] == 4  # first block written is block 4
        expected_tlv = _build_ndef_text_tlv("apple:1440903625")
        assert first_call[0][1] == expected_tlv[0:4]

    def test_write_tag_raises_on_locked_tag(self):
        mock_pn532 = MagicMock()
        mock_pn532.ntag2xx_write_block.return_value = False
        nfc = self._make_nfc(mock_pn532)
        with pytest.raises(IOError, match="locked"):
            nfc.write_tag("apple:1440903625")

    def test_write_url_tag_writes_uri_record(self):
        from nfc_interface import _build_ndef_uri_tlv
        mock_pn532 = MagicMock()
        mock_pn532.ntag2xx_write_block.return_value = True
        nfc = self._make_nfc(mock_pn532)
        result = nfc.write_url_tag("http://vinyl-pi.local:5000")
        assert result is True
        first_call = mock_pn532.ntag2xx_write_block.call_args_list[0]
        expected_tlv = _build_ndef_uri_tlv("http://vinyl-pi.local:5000")
        assert first_call[0][1] == expected_tlv[0:4]

    def test_write_url_tag_raises_on_locked_tag(self):
        mock_pn532 = MagicMock()
        mock_pn532.ntag2xx_write_block.return_value = False
        nfc = self._make_nfc(mock_pn532)
        with pytest.raises(IOError, match="locked"):
            nfc.write_url_tag("http://vinyl-pi.local:5000")

    def test_read_tag_stops_reading_when_block_returns_none(self):
        mock_pn532 = MagicMock()
        mock_pn532.read_passive_target.return_value = b"\x04\x12\x34\x56"
        mock_pn532.ntag2xx_read_block.return_value = None  # immediate None on first block
        nfc = self._make_nfc(mock_pn532)
        result = nfc.read_tag()
        assert result is None
        assert mock_pn532.ntag2xx_read_block.call_count == 1  # stopped at first None
