"""Download only the MongoDB executable from MongoDB's official Windows ZIP.

Uses ZIP range reads to avoid downloading large, unnecessary debug symbols.
The extracted entry is verified against the official archive's CRC32.
"""
import pathlib, struct, urllib.request, zlib

URL = "https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-8.0.16.zip"
ROOT = pathlib.Path(__file__).resolve().parents[1]

def fetch_range(start, end):
    req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(req, timeout=120) as response:
        if response.status != 206:
            raise RuntimeError("Server must support byte ranges")
        return response.read()

def main():
    target = ROOT / "tools/mongodb/bin/mongod.exe"
    if target.exists():
        print("MongoDB executable already available")
        return
    with urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=30) as response:
        size = int(response.headers["Content-Length"])
    tail = fetch_range(size - 65536, size - 1)
    eocd = tail.rfind(b"PK\x05\x06")
    _, _, _, _, _, central_size, central_start, _ = struct.unpack_from("<4s4H2IH", tail, eocd)
    central = fetch_range(central_start, central_start + central_size - 1)
    offset = 0
    while offset < len(central):
        entry = struct.unpack_from("<4s6H3I5H2I", central, offset)
        if entry[0] != b"PK\x01\x02":
            raise RuntimeError("Invalid ZIP central directory")
        method, crc, compressed = entry[4], entry[7], entry[8]
        name_len, extra_len, comment_len, local_offset = entry[10], entry[11], entry[12], entry[16]
        name = central[offset + 46:offset + 46 + name_len].decode()
        offset += 46 + name_len + extra_len + comment_len
        if name.endswith("/bin/mongod.exe"):
            header = fetch_range(local_offset, local_offset + 29)
            name_length, extra_length = struct.unpack_from("<HH", header, 26)
            start = local_offset + 30 + name_length + extra_length
            print(f"Downloading MongoDB executable ({compressed // 1048576} MiB)", flush=True)
            payload = fetch_range(start, start + compressed - 1)
            raw = zlib.decompress(payload, -15) if method == 8 else payload
            if zlib.crc32(raw) & 0xFFFFFFFF != crc:
                raise RuntimeError("MongoDB archive CRC32 verification failed")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            print("Official MongoDB executable extracted and CRC32 verified")
            return
    raise RuntimeError("mongod.exe not found in official archive")

if __name__ == "__main__":
    main()
