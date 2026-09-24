import os
from pathlib import Path
from typing import Generator
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, Response

def send_partial_file(path: Path, request: Request, media_type: str, chunk_size: int = 1024 * 1024) -> Response:
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    file_size = path.stat().st_size
    range_header = request.headers.get("Range")

    if not range_header:
        def iter_full() -> Generator[bytes, None, None]:
            with open(path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk

        headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
            "Content-Length": str(file_size),
            "Content-Type": media_type,
        }
        return StreamingResponse(iter_full(), status_code=200, headers=headers, media_type=media_type)

    # Format: Range: bytes=start-end
    try:
        units, range_val = range_header.strip().split("=")
        if units != "bytes":
            raise ValueError()
        
        parts = range_val.split("-")
        start_str = parts[0].strip()
        end_str = parts[1].strip() if len(parts) > 1 else ""

        if start_str and end_str:
            start = int(start_str)
            # RFC 9110: an end past the file is clamped, not rejected with 416
            end = min(int(end_str), file_size - 1)
        elif start_str:
            start = int(start_str)
            end = file_size - 1
        elif end_str:
            # Suffix range: -500 means last 500 bytes
            suffix = int(end_str)
            start = max(0, file_size - suffix)
            end = file_size - 1
        else:
            raise ValueError()

        if start >= file_size or start > end:
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{file_size}"}
            )

    except Exception:
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}"}
        )

    content_length = end - start + 1

    def iter_range() -> Generator[bytes, None, None]:
        with open(path, "rb") as f:
            f.seek(start)
            bytes_left = content_length
            while bytes_left > 0:
                current_read = min(chunk_size, bytes_left)
                data = f.read(current_read)
                if not data:
                    break
                bytes_left -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
        "Content-Length": str(content_length),
        "Content-Type": media_type,
    }
    return StreamingResponse(iter_range(), status_code=206, headers=headers, media_type=media_type)
