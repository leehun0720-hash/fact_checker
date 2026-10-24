"""Bound upload bodies before multipart parsing and stream files to disk."""
from pathlib import Path

from fastapi import HTTPException, UploadFile
from starlette.responses import JSONResponse

from .config import settings


class UploadBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path").rstrip("/") != "/api/jobs":
            return await self.app(scope, receive, send)
        # A small, bounded allowance covers multipart headers and text fields.
        limit = settings.max_total_upload_mb * 1024 * 1024 + 1024 * 1024
        lengths = [v for k, v in scope.get("headers", []) if k.lower() == b"content-length"]
        try:
            if len(lengths) > 1 or (lengths and int(lengths[0]) < 0):
                raise ValueError
            if lengths and int(lengths[0]) > limit:
                return await JSONResponse({"detail": "요청 전체 크기 제한을 초과했습니다."}, status_code=413)(scope, receive, send)
        except ValueError:
            return await JSONResponse({"detail": "잘못된 Content-Length입니다."}, status_code=400)(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, "요청 전체 크기 제한을 초과했습니다.")
            return message

        await self.app(scope, limited_receive, send)


async def save_upload(upload: UploadFile, target: Path, remaining: int) -> int:
    limit = min(settings.max_upload_mb * 1024 * 1024, remaining)
    size = 0
    with target.open("xb") as output:
        while True:
            chunk = await upload.read(min(1024 * 1024, max(1, limit - size + 1)))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, "파일 또는 첨부 전체 크기 제한을 초과했습니다.")
            output.write(chunk)
    return size
