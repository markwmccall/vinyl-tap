import logging

log = logging.getLogger(__name__)


def _parse_ndef_text(data):
    """Extract text string from NDEF TLV bytes. Returns string or None if blank/unrecognised."""
    if not data or data[0] != 0x03:
        return None
    length = data[1]
    record_start = 2
    if length == 0xFF:  # 3-byte length encoding (rare for NTAG213)
        length = (data[2] << 8) | data[3]
        record_start = 4
    record = data[record_start:record_start + length]
    if len(record) < 4:
        return None
    type_len = record[1]
    payload_len = record[2]
    rec_type = record[3:3 + type_len]
    payload = record[3 + type_len:3 + type_len + payload_len]
    if rec_type == b'T' and len(payload) > 0:
        lang_len = payload[0] & 0x3F
        return payload[1 + lang_len:].decode("utf-8", errors="replace")
    return None


def _build_ndef_text_tlv(text):
    """Build padded NDEF TLV bytes for a UTF-8 text record (language = 'en')."""
    payload = bytes([0x02, 0x65, 0x6E]) + text.encode("utf-8")  # 0x02=lang_len, "en"
    record = bytes([0xD1, 0x01, len(payload), 0x54]) + payload  # 0x54 = 'T'
    tlv = bytes([0x03, len(record)]) + record + bytes([0xFE])
    return tlv + bytes((-len(tlv)) % 4)  # pad to 4-byte block boundary


def _build_ndef_uri_tlv(url):
    """Build padded NDEF TLV bytes for a URI record."""
    if url.startswith("https://"):
        prefix_code, body = 0x04, url[len("https://"):]
    elif url.startswith("http://"):
        prefix_code, body = 0x03, url[len("http://"):]
    else:
        prefix_code, body = 0x00, url
    payload = bytes([prefix_code]) + body.encode("utf-8")
    record = bytes([0xD1, 0x01, len(payload), 0x55]) + payload  # 0x55 = 'U'
    tlv = bytes([0x03, len(record)]) + record + bytes([0xFE])
    return tlv + bytes((-len(tlv)) % 4)


def parse_tag_data(tag_string):
    """Parse an NDEF tag string into a dict with 'service', 'type', and 'id'.

    Supported formats:
      {service}:{collection_id}          -> {"service": "...", "type": "album", "id": "..."}
      {service}:track:{track_id}         -> {"service": "...", "type": "track", "id": "..."}
      {service}:playlist:{playlist_id}   -> {"service": "...", "type": "playlist", "id": "..."}

    Raises ValueError only for structurally invalid strings (no colon, empty parts).
    Unknown services parse successfully; provider lookup raises KeyError later.
    """
    if not tag_string or ":" not in tag_string:
        raise ValueError(f"Unrecognised tag format: {tag_string!r}")
    service, _, rest = tag_string.partition(":")
    if not service or not rest:
        raise ValueError(f"Unrecognised tag format: {tag_string!r}")
    if rest.startswith("track:"):
        track_id = rest[len("track:"):]
        if not track_id:
            raise ValueError(f"Unrecognised tag format: {tag_string!r}")
        return {"service": service, "type": "track", "id": track_id}
    if rest.startswith("playlist:"):
        playlist_id = rest[len("playlist:"):]
        if not playlist_id:
            raise ValueError(f"Unrecognised tag format: {tag_string!r}")
        return {"service": service, "type": "playlist", "id": playlist_id}
    return {"service": service, "type": "album", "id": rest}


class MockNFC:
    """Mac/testing NFC implementation - reads from stdin, writes to stdout."""

    def read_tag(self):
        """Block until the user types a tag string and presses Enter."""
        return input("Tap card (or type tag): ")

    def write_tag(self, data):
        """Print what would be written to the physical tag."""
        log.info(f"[MockNFC] Would write: {data}")
        return True

    def write_url_tag(self, url):
        """Print what URL would be written to the physical tag."""
        log.info(f"[MockNFC] Would write URL: {url}")
        return True


class PN532NFC:
    """Raspberry Pi NFC implementation using the Waveshare PN532 HAT via I2C.

    Expects the HAT jumpers configured for I2C mode (I0=H, I1=L) with
    RSTPDN connected to GPIO20 (D20) for software reset after I2C failures.
    INT0→D16 jumper connected per Waveshare docs but unused by this driver.

    The Adafruit PN532 I2C library ignores the irq= parameter — _wait_ready()
    always polls via I2C status byte reads. Clock-stretch protection comes from
    the kernel: ``options i2c_bcm2835 clk_tout_ms=200`` (set by setup.sh,
    requires power-cycle to apply). Without this, a hung PN532 blocks the I2C
    bus indefinitely with no error propagation to the watchdog.
    """

    def __init__(self):
        import board
        import busio
        from adafruit_pn532.i2c import PN532_I2C
        i2c = busio.I2C(board.SCL, board.SDA)
        self._pn532 = PN532_I2C(i2c, debug=False, reset=board.D20)
        self._pn532.SAM_configuration()

    def reset(self):
        """Hardware-reset the PN532 via RSTPDN (D20) and re-initialise.

        Called by the NFC polling loop after repeated I2C failures. Recovers
        the PN532 without requiring a power cycle of the Pi.
        """
        self._pn532.reset()
        self._pn532.SAM_configuration()

    def read_tag(self):
        """Poll once (0.5 s timeout). Return NDEF text string, or None if no card / blank."""
        uid = self._pn532.read_passive_target(timeout=0.5)
        if uid is None:
            return None
        data = bytearray()
        for block in range(4, 16):  # up to 48 bytes - sufficient for NTAG213 NDEF
            b = self._pn532.ntag2xx_read_block(block)
            if b is None:
                break
            data.extend(b)
        return _parse_ndef_text(bytes(data))

    def _write_block(self, block_num, data):
        """Write one block, raising IOError on failure or missing tag."""
        try:
            result = self._pn532.ntag2xx_write_block(block_num, data)
        except TypeError:
            raise IOError("Tag write failed — tag removed or no response from reader")
        if not result:
            raise IOError("Tag is read-only (locked)")

    def write_tag(self, data):
        """Write NDEF text record. Raises IOError if tag is locked (read-only)."""
        tlv = _build_ndef_text_tlv(data)
        for i, block_num in enumerate(range(4, 4 + len(tlv) // 4)):
            self._write_block(block_num, tlv[i * 4:(i + 1) * 4])
        return True

    def write_url_tag(self, url):
        """Write NDEF URI record. Raises IOError if tag is locked (read-only)."""
        tlv = _build_ndef_uri_tlv(url)
        for i, block_num in enumerate(range(4, 4 + len(tlv) // 4)):
            self._write_block(block_num, tlv[i * 4:(i + 1) * 4])
        return True
