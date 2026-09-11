"""Enable standard PE security characteristics on bundled Windows binaries."""
from pathlib import Path
import struct
import sys

IMAGE_FILE_DLL = 0x2000
IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE = 0x0040
IMAGE_DLLCHARACTERISTICS_NX_COMPAT = 0x0100
IMAGE_DLLCHARACTERISTICS_TERMINAL_SERVER_AWARE = 0x8000
IMAGE_DLLCHARACTERISTICS_HIGH_ENTROPY_VA = 0x0020


def patch(path: Path) -> bool:
    data = bytearray(path.read_bytes())
    if data[:2] != b"MZ":
        return False
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        return False
    coff = pe_offset + 4
    machine, sections, _, _, _, optional_size, _ = struct.unpack_from("<HHIIIHH", data, coff)
    optional = coff + 20
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic not in (0x10B, 0x20B) or optional_size < 0x48:
        return False

    # Refuse to claim ASLR support if the image has no relocation directory.
    number_rva = struct.unpack_from("<I", data, optional + (92 if magic == 0x10B else 108))[0]
    directory = optional + (96 if magic == 0x10B else 112)
    if number_rva <= 5 or directory + 8 * 6 > len(data):
        return False
    reloc_rva, reloc_size = struct.unpack_from("<II", data, directory + 8 * 5)
    if not reloc_rva or not reloc_size:
        return False

    characteristics = struct.unpack_from("<H", data, optional + 0x46)[0]
    flags = (IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE |
             IMAGE_DLLCHARACTERISTICS_NX_COMPAT |
             IMAGE_DLLCHARACTERISTICS_TERMINAL_SERVER_AWARE)
    if magic == 0x20B:
        flags |= IMAGE_DLLCHARACTERISTICS_HIGH_ENTROPY_VA
    updated = characteristics | flags
    if updated == characteristics:
        return False
    struct.pack_into("<H", data, optional + 0x46, updated)
    path.write_bytes(data)
    return True


def main(root: Path) -> int:
    changed = []
    for path in root.rglob("*"):
        if path.suffix.lower() not in (".exe", ".dll"):
            continue
        try:
            if patch(path):
                changed.append(str(path))
        except (OSError, struct.error) as exc:
            raise SystemExit(f"Unable to inspect {path}: {exc}") from exc
    print("PE security characteristics updated:")
    print("\n".join(changed) if changed else "(none required)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_pe_security.py <PyInstaller output directory>")
    raise SystemExit(main(Path(sys.argv[1])))
