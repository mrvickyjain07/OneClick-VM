import os
import requests
from pathlib import Path
from .logger import get_logger

logger = get_logger("ISOManager")

CHUNK_SIZE = 65536  # 64 KB


class ISOManager:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_iso_path(self, filename: str) -> Path:
        return self.cache_dir / filename

    def is_downloaded(self, filename: str) -> bool:
        p = self.get_iso_path(filename)
        return p.exists() and p.stat().st_size > 0

    def download_iso(
        self,
        url: str,
        filename: str,
        progress_callback=None,
        pause_check_callback=None,
        cancel_check_callback=None,
    ) -> Path:
        dest = self.get_iso_path(filename)
        tmp = dest.with_suffix(".part")

        downloaded = tmp.stat().st_size if tmp.exists() else 0
        headers = {"Range": f"bytes={downloaded}-"} if downloaded else {}

        try:
            response = requests.get(
                url,
                stream=True,
                timeout=(10, 60),
                headers=headers,
                allow_redirects=True,
            )
            response.raise_for_status()

            total_size = int(response.headers.get("Content-Length", 0)) + downloaded
            accept_ranges = response.headers.get("Accept-Ranges", "none") != "none"

            mode = "ab" if (downloaded and accept_ranges) else "wb"
            if mode == "wb":
                downloaded = 0

            with open(tmp, mode) as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if cancel_check_callback and cancel_check_callback():
                        logger.info("Download cancelled by user.")
                        return None

                    while pause_check_callback and pause_check_callback():
                        import time; time.sleep(0.3)

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            pct = int(downloaded * 100 / total_size)
                            progress_callback(pct)

            tmp.rename(dest)
            logger.info(f"Download complete: {dest}")
            return dest

        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise
