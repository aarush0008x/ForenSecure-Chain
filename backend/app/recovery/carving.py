from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CarveCandidate:
    file_type: str
    extension: str
    start_offset: int
    end_offset: int
    data: bytes
    metadata: dict[str, object]


def _jpeg_metadata(data: bytes, start: int) -> dict[str, object]:
    position = start + 2
    sof_markers = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
    while position + 9 < len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        marker = data[position] if position < len(data) else None
        if marker in {0xD8, 0xD9}:
            position += 1
            continue
        if marker == 0xDA or marker is None or position + 2 >= len(data):
            break
        segment_length = int.from_bytes(data[position + 1 : position + 3], "big")
        if marker in sof_markers and position + 7 < len(data):
            return {
                "dimensions": {
                    "width": int.from_bytes(data[position + 5 : position + 7], "big"),
                    "height": int.from_bytes(data[position + 3 : position + 5], "big"),
                },
                "dimensions_source": "actual",
            }
        position += max(segment_length, 2)
    return {}


def _jpeg_carver(data: bytes) -> list[CarveCandidate]:
    candidates: list[CarveCandidate] = []
    cursor = 0
    while (start := data.find(b"\xff\xd8\xff", cursor)) != -1:
        end_marker = data.find(b"\xff\xd9", start + 3)
        if end_marker == -1:
            break
        end = end_marker + 2
        candidates.append(
            CarveCandidate(
                file_type="image/jpeg",
                extension="jpg",
                start_offset=start,
                end_offset=end,
                data=data[start:end],
                metadata={
                    "actual": {"format": "JPEG", "signature": "FF D8 FF", **_jpeg_metadata(data[start:end], 0)},
                    "inferred": {"boundary": "JPEG EOI marker FF D9"},
                },
            )
        )
        cursor = end
    return candidates


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"


def _png_carver(data: bytes) -> list[CarveCandidate]:
    candidates: list[CarveCandidate] = []
    cursor = 0
    while (start := data.find(PNG_SIGNATURE, cursor)) != -1:
        end_marker = data.find(PNG_IEND, start + len(PNG_SIGNATURE))
        if end_marker == -1:
            break
        end = end_marker + len(PNG_IEND)
        actual: dict[str, object] = {"format": "PNG", "signature": "89 50 4E 47"}
        if data[start + 12 : start + 16] == b"IHDR" and len(data) >= start + 24:
            actual["dimensions"] = {
                "width": int.from_bytes(data[start + 16 : start + 20], "big"),
                "height": int.from_bytes(data[start + 20 : start + 24], "big"),
            }
            actual["dimensions_source"] = "actual"
        candidates.append(
            CarveCandidate(
                file_type="image/png",
                extension="png",
                start_offset=start,
                end_offset=end,
                data=data[start:end],
                metadata={
                    "actual": actual,
                    "inferred": {"boundary": "PNG IEND marker"},
                },
            )
        )
        cursor = end
    return candidates


def _pdf_carver(data: bytes) -> list[CarveCandidate]:
    candidates: list[CarveCandidate] = []
    cursor = 0
    while (start := data.find(b"%PDF-", cursor)) != -1:
        end_marker = data.find(b"%%EOF", start + 5)
        if end_marker == -1:
            break
        end = end_marker + len(b"%%EOF")
        version_end = data.find(b"\n", start, min(start + 16, len(data)))
        version = data[start:version_end if version_end != -1 else start + 9].decode(
            "ascii", errors="replace"
        )
        candidates.append(
            CarveCandidate(
                file_type="application/pdf",
                extension="pdf",
                start_offset=start,
                end_offset=end,
                data=data[start:end],
                metadata={
                    "actual": {"format": "PDF", "signature": "%PDF-", "version": version},
                    "inferred": {"boundary": "PDF %%EOF marker"},
                },
            )
        )
        cursor = end
    return candidates


def _zip_carver(data: bytes) -> list[CarveCandidate]:
    candidates: list[CarveCandidate] = []
    cursor = 0
    ZIP_SIG = b"PK\x03\x04"
    EOCD_SIG = b"PK\x05\x06"
    while (start := data.find(ZIP_SIG, cursor)) != -1:
        eocd = data.find(EOCD_SIG, start + 4)
        if eocd == -1:
            break
        # EOCD record is 22 bytes + comment length
        comment_len = 0
        if eocd + 22 <= len(data):
            comment_len = int.from_bytes(data[eocd + 20 : eocd + 22], "little")
        end = min(eocd + 22 + comment_len, len(data))
        candidates.append(
            CarveCandidate(
                file_type="application/zip",
                extension="zip",
                start_offset=start,
                end_offset=end,
                data=data[start:end],
                metadata={
                    "actual": {"format": "ZIP Archive", "signature": "PK 03 04"},
                    "inferred": {"boundary": "ZIP EOCD record PK 05 06"},
                },
            )
        )
        cursor = end
    return candidates


def _gif_carver(data: bytes) -> list[CarveCandidate]:
    candidates: list[CarveCandidate] = []
    cursor = 0
    while cursor < len(data):
        start = -1
        for sig in (b"GIF87a", b"GIF89a"):
            pos = data.find(sig, cursor)
            if pos != -1 and (start == -1 or pos < start):
                start = pos
        if start == -1:
            break
        trailer = data.find(b"\x3b", start + 6)
        if trailer == -1:
            break
        end = trailer + 1
        width = int.from_bytes(data[start + 6 : start + 8], "little") if len(data) >= start + 8 else 0
        height = int.from_bytes(data[start + 8 : start + 10], "little") if len(data) >= start + 10 else 0
        candidates.append(
            CarveCandidate(
                file_type="image/gif",
                extension="gif",
                start_offset=start,
                end_offset=end,
                data=data[start:end],
                metadata={
                    "actual": {
                        "format": "GIF",
                        "signature": data[start : start + 6].decode("ascii", errors="replace"),
                        "dimensions": {"width": width, "height": height},
                        "dimensions_source": "actual",
                    },
                    "inferred": {"boundary": "GIF trailer 3B"},
                },
            )
        )
        cursor = end
    return candidates


CARVER_REGISTRY: tuple[Callable[[bytes], list[CarveCandidate]], ...] = (
    _jpeg_carver,
    _png_carver,
    _pdf_carver,
    _zip_carver,
    _gif_carver,
)


def carve(data: bytes) -> list[CarveCandidate]:
    """Run all registered signature carvers and return source-order candidates."""
    candidates = [candidate for carver in CARVER_REGISTRY for candidate in carver(data)]
    return sorted(candidates, key=lambda candidate: candidate.start_offset)