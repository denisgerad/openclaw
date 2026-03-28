"""
core/downloads_watcher.py
──────────────────────────
Downloads watcher: monitors a folder for new .tar.gz / .zip files
and automatically surfaces them as HIL ingest proposals in Streamlit.

Flow:
  1. Watcher runs in a background thread (watchdog)
  2. When a new archive appears in OPENCLAW_DOWNLOADS_DIR, it is
     added to a thread-safe queue
  3. Streamlit app polls the queue each render cycle
  4. New files appear as HIL proposals in the Projects tab —
     user clicks Approve / Reject / Edit exactly as if they
     had uploaded via the file-uploader widget

Supported formats:  .tar.gz  .tgz  .zip
Default watch dir:  ~/Downloads  (override via OPENCLAW_DOWNLOADS_DIR)

This means: when you download a tarball from Claude in your browser,
OpenClaw detects it within a few seconds and shows the HIL panel
automatically — no manual upload step needed.
"""

import os
import time
import queue
import threading
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent


WATCHED_EXTENSIONS = {".tar.gz", ".tgz", ".tar", ".tar.bz2", ".zip"}
# Minimum file age in seconds before proposing (avoids partial downloads)
MIN_AGE_SECONDS = 2


def _is_archive(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(ext) for ext in WATCHED_EXTENSIONS)


def _is_stable(path: Path) -> bool:
    """Return True if file hasn't been modified in MIN_AGE_SECONDS (download complete)."""
    try:
        age = time.time() - path.stat().st_mtime
        return age >= MIN_AGE_SECONDS and path.stat().st_size > 0
    except OSError:
        return False


class _ArchiveHandler(FileSystemEventHandler):
    """Watchdog event handler — pushes stable archive paths to a queue."""

    def __init__(self, new_file_queue: queue.Queue):
        self._queue    = new_file_queue
        self._seen: set[str] = set()

    def _maybe_enqueue(self, path_str: str):
        p = Path(path_str)
        if not _is_archive(p) or path_str in self._seen:
            return
        # Wait briefly for download to complete
        for _ in range(10):
            if _is_stable(p):
                self._seen.add(path_str)
                self._queue.put(str(p))
                return
            time.sleep(0.5)

    def on_created(self, event: FileCreatedEvent):
        if not event.is_directory:
            threading.Thread(
                target=self._maybe_enqueue,
                args=(event.src_path,),
                daemon=True,
            ).start()

    def on_moved(self, event: FileMovedEvent):
        # Handles browser "download complete" rename (e.g. .part → .tar.gz)
        if not event.is_directory:
            threading.Thread(
                target=self._maybe_enqueue,
                args=(event.dest_path,),
                daemon=True,
            ).start()


class DownloadsWatcher:
    """
    Background thread that watches the downloads folder and queues
    new archive files for HIL ingest review.

    Usage (in Streamlit app):
        watcher = DownloadsWatcher()
        watcher.start()

        # On each render:
        new_file = watcher.poll()
        if new_file:
            proposal = ctx.pm.propose_ingest(new_file)
            st.session_state.ingest_proposal = proposal
            st.session_state.proj_hil_state  = "ingest"
            st.rerun()
    """

    def __init__(self, watch_dir: Optional[str] = None):
        env_dir    = os.getenv("OPENCLAW_DOWNLOADS_DIR")
        resolved   = watch_dir or env_dir or str(Path.home() / "Downloads")
        self.watch_dir = Path(resolved).expanduser().resolve()
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._queue:    queue.Queue = queue.Queue()
        self._observer: Optional[Observer] = None
        self._running   = False

    def start(self):
        if self._running:
            return
        handler          = _ArchiveHandler(self._queue)
        self._observer   = Observer()
        self._observer.schedule(handler, str(self.watch_dir), recursive=False)
        self._observer.start()
        self._running    = True

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()
        self._running = False

    def poll(self) -> Optional[str]:
        """
        Return the next queued file path, or None if nothing new.
        Non-blocking — safe to call on every Streamlit render.
        """
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def poll_all(self) -> list[str]:
        """Return all queued files at once."""
        files = []
        while True:
            try:
                files.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return files

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def watch_path(self) -> str:
        return str(self.watch_dir)
