"""
core/project_manager.py
────────────────────────
ProjectManager: file versioning for OpenClaw projects.

HIL contract:
  ingest() NEVER writes files directly.
  It returns an IngestProposal that the HIL layer presents to the human.
  Only after approval does execute_ingest() perform the actual extraction.

Project folder layout (root configured via .env):
  <PROJECT_ROOT>/
  ├── project.json       ← manifest (name, versions[], active_version)
  ├── versions/
  │   ├── v1/            ← unzipped contents
  │   ├── v2/
  │   └── v3/            ← current
  ├── kb/                ← ChromaDB (KnowledgeBase)
  └── notes/             ← NotesEngine

.env key: OPENCLAW_PROJECT_<NAME_UPPER>
e.g.      OPENCLAW_PROJECT_CYBERSHIELD=/home/dennis/projects/cybershield
"""

import os
import json
import shutil
import tarfile
import zipfile
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

MANIFEST_FILE = "project.json"
VERSIONS_DIR  = "versions"
KB_DIR        = "kb"
NOTES_DIR     = "notes"


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ProjectVersion:
    name:      str
    path:      Path
    timestamp: str = ""
    source:    str = ""        # original filename
    sha256:    str = ""
    size_kb:   float = 0.0
    file_count: int = 0
    notes:     str = ""

    def to_dict(self) -> dict:
        return {
            "name":       self.name,
            "timestamp":  self.timestamp,
            "source":     self.source,
            "sha256":     self.sha256,
            "size_kb":    self.size_kb,
            "file_count": self.file_count,
            "notes":      self.notes,
        }


@dataclass
class IngestProposal:
    """
    Staged ingestion request — presented to HIL before any files are written.
    Fields are informational; execute_ingest() uses source_path + version_name.
    """
    project_name:  str
    source_path:   Path
    version_name:  str              # e.g. "v3"
    dest_path:     Path             # where it WILL go after approval
    archive_type:  str              # "tar.gz" | "zip" | "dir"
    sha256:        str
    size_kb:       float
    file_list:     list[str]        # top-level entries in archive
    notes:         str = ""         # editable by human before approval
    # HIL decision
    decision:      str = ""         # "approved" | "rejected" | "edited"


# ── ProjectManager ────────────────────────────────────────────────────────────

class ProjectManager:
    """
    Manages a single named project: folder structure, manifest, versioning.
    All write operations are HIL-gated via propose_ingest() → execute_ingest().
    """

    def __init__(self, project_name: str):
        self.name = project_name.lower().strip()
        self.root = self._resolve_root()
        self._ensure_structure()

    # ── Root resolution ───────────────────────────────────────────────────────

    def _resolve_root(self) -> Path:
        env_key = f"OPENCLAW_PROJECT_{self.name.upper()}"
        env_val = os.getenv(env_key)
        if env_val:
            return Path(env_val).expanduser().resolve()
        return Path.home() / "openclaw" / "projects" / self.name

    def _ensure_structure(self):
        for sub in [VERSIONS_DIR, KB_DIR, NOTES_DIR]:
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        if not self._manifest_path.exists():
            self._write_manifest({
                "name":           self.name,
                "created":        datetime.now(timezone.utc).isoformat(),
                "active_version": None,
                "versions":       [],
                "description":    "",
                "root":           str(self.root),
            })

    @property
    def _manifest_path(self) -> Path:
        return self.root / MANIFEST_FILE

    # ── Manifest ──────────────────────────────────────────────────────────────

    def read_manifest(self) -> dict:
        with open(self._manifest_path) as f:
            return json.load(f)

    def _write_manifest(self, data: dict):
        with open(self._manifest_path, "w") as f:
            json.dump(data, f, indent=2)

    def set_description(self, desc: str):
        m = self.read_manifest()
        m["description"] = desc
        self._write_manifest(m)

    # ── Version queries ───────────────────────────────────────────────────────

    def list_versions(self) -> list[ProjectVersion]:
        manifest = self.read_manifest()
        result = []
        for v in manifest["versions"]:
            path = self.root / VERSIONS_DIR / v["name"]
            result.append(ProjectVersion(
                name=v["name"], path=path,
                timestamp=v.get("timestamp", ""),
                source=v.get("source", ""),
                sha256=v.get("sha256", ""),
                size_kb=v.get("size_kb", 0),
                file_count=v.get("file_count", 0),
                notes=v.get("notes", ""),
            ))
        return result

    def get_active_version(self) -> Optional[ProjectVersion]:
        m = self.read_manifest()
        name = m.get("active_version")
        if not name:
            return None
        for v in m["versions"]:
            if v["name"] == name:
                return ProjectVersion(
                    name=name,
                    path=self.root / VERSIONS_DIR / name,
                    **{k: v.get(k, "") for k in ["timestamp","source","sha256","notes"]},
                    size_kb=v.get("size_kb", 0),
                    file_count=v.get("file_count", 0),
                )
        return None

    def _next_version_name(self) -> str:
        m = self.read_manifest()
        return f"v{len(m['versions']) + 1}"

    # ── HIL Step 1: Propose (no side effects) ─────────────────────────────────

    def propose_ingest(self, file_path: str) -> IngestProposal:
        """
        Inspect a downloaded file and build an IngestProposal.
        Does NOT extract or copy anything — pure analysis only.
        Returns proposal for HIL to review.
        """
        src = Path(file_path).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"File not found: {src}")

        name       = self._next_version_name()
        dest       = self.root / VERSIONS_DIR / name
        size_kb    = round(src.stat().st_size / 1024, 1)
        sha256     = self._sha256(src)
        arch_type, file_list = self._inspect_archive(src)

        return IngestProposal(
            project_name = self.name,
            source_path  = src,
            version_name = name,
            dest_path    = dest,
            archive_type = arch_type,
            sha256       = sha256,
            size_kb      = size_kb,
            file_list    = file_list,
        )

    # ── HIL Step 2: Execute (called only after approval) ──────────────────────

    def execute_ingest(self, proposal: IngestProposal) -> ProjectVersion:
        """
        Perform the actual extraction after HIL approval.
        Called ONLY by hil/project_approver.py after human confirmation.
        """
        dest = proposal.dest_path
        dest.mkdir(parents=True, exist_ok=True)

        # Extract
        src = proposal.source_path
        if proposal.archive_type == "tar.gz":
            with tarfile.open(src, "r:gz") as tf:
                tf.extractall(dest)
        elif proposal.archive_type == "tar.bz2":
            with tarfile.open(src, "r:bz2") as tf:
                tf.extractall(dest)
        elif proposal.archive_type == "tar":
            with tarfile.open(src, "r:") as tf:
                tf.extractall(dest)
        elif proposal.archive_type == "zip":
            with zipfile.ZipFile(src) as zf:
                zf.extractall(dest)
        elif proposal.archive_type == "dir":
            shutil.copytree(str(src), str(dest), dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest / src.name)

        # Count extracted files
        file_count = sum(1 for _ in dest.rglob("*") if _.is_file())

        version = ProjectVersion(
            name       = proposal.version_name,
            path       = dest,
            timestamp  = datetime.now(timezone.utc).isoformat(),
            source     = src.name,
            sha256     = proposal.sha256,
            size_kb    = proposal.size_kb,
            file_count = file_count,
            notes      = proposal.notes,
        )

        # Register in manifest
        m = self.read_manifest()
        m["versions"].append(version.to_dict())
        m["active_version"] = version.name
        self._write_manifest(m)

        return version

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]   # first 16 chars is enough for display

    @staticmethod
    def _inspect_archive(path: Path) -> tuple[str, list[str]]:
        """Return (archive_type, top_level_file_list)."""
        name = path.name.lower()
        try:
            if name.endswith(".tar.gz") or name.endswith(".tgz"):
                with tarfile.open(path, "r:gz") as tf:
                    members = tf.getnames()
                return "tar.gz", members[:20]
            elif name.endswith(".tar.bz2"):
                with tarfile.open(path, "r:bz2") as tf:
                    members = tf.getnames()
                return "tar.bz2", members[:20]
            elif name.endswith(".tar"):
                with tarfile.open(path, "r:") as tf:
                    members = tf.getnames()
                return "tar", members[:20]
            elif name.endswith(".zip"):
                with zipfile.ZipFile(path) as zf:
                    members = zf.namelist()
                return "zip", members[:20]
            elif path.is_dir():
                members = [str(p.relative_to(path)) for p in path.iterdir()]
                return "dir", members[:20]
            else:
                return "file", [path.name]
        except Exception as e:
            return "unknown", [f"(could not inspect: {e})"]

    # ── Project registry ──────────────────────────────────────────────────────

    @staticmethod
    def list_all_projects() -> list[str]:
        """
        Discover all projects from environment variables named OPENCLAW_PROJECT_*.
        Also scans the default ~/openclaw/projects/ folder.
        """
        found = set()
        for key, val in os.environ.items():
            if key.startswith("OPENCLAW_PROJECT_"):
                found.add(key[len("OPENCLAW_PROJECT_"):].lower())
        default_base = Path.home() / "openclaw" / "projects"
        if default_base.exists():
            for p in default_base.iterdir():
                if p.is_dir() and (p / MANIFEST_FILE).exists():
                    found.add(p.name)
        return sorted(found)
