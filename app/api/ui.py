from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["ui"], include_in_schema=False)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/")
def kiosk_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
