"""
Note writer — writes decision logs and learning memos to vault.
Creates HEMS/ directory structure in the vault.
"""
from datetime import datetime
from pathlib import Path
from loguru import logger


class NoteWriter:
    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path)
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Create HEMS output directories if they don't exist."""
        (self.vault_path / "HEMS" / "decisions").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "HEMS" / "learnings").mkdir(parents=True, exist_ok=True)

    def write_decision_log(self, trigger: str, action: str, context: str = "") -> str:
        """Append a decision entry to today's decision log.

        Returns the relative path of the written file.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H:%M")
        rel_path = f"HEMS/decisions/{today}.md"
        full_path = self.vault_path / rel_path

        if not full_path.exists():
            # Create new daily file with frontmatter
            header = f"""---
tags: [hems, decision-log, auto-generated]
date: {today}
---
# Decision Log: {today}
"""
            full_path.write_text(header, encoding="utf-8")

        # Append entry
        entry = f"""
## {time_str} — {trigger}
- **アクション**: {action}
"""
        if context:
            entry += f"- **コンテキスト**: {context}\n"

        with open(full_path, "a", encoding="utf-8") as f:
            f.write(entry)

        logger.debug(f"Decision log appended: {rel_path}")
        return rel_path

    def write_learning_memo(self, title: str, content: str) -> str:
        """Append a learning entry to today's learning memo.

        Returns the relative path of the written file.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H:%M")
        rel_path = f"HEMS/learnings/{today}.md"
        full_path = self.vault_path / rel_path

        if not full_path.exists():
            header = f"""---
tags: [hems, learning, auto-generated]
date: {today}
---
# Learning Memo: {today}
"""
            full_path.write_text(header, encoding="utf-8")

        entry = f"""
## {time_str} — {title}
{content}
"""
        with open(full_path, "a", encoding="utf-8") as f:
            f.write(entry)

        logger.debug(f"Learning memo appended: {rel_path}")
        return rel_path

    def write_note(self, rel_path: str, content: str, tags: list[str] | None = None) -> str:
        """Write arbitrary note to vault (within HEMS/ directory only).

        Returns the relative path of the written file.
        Raises ValueError if the resolved path escapes the vault boundary.
        """
        # Safety: only allow writing under HEMS/
        if not rel_path.startswith("HEMS/"):
            rel_path = f"HEMS/{rel_path}"

        # Ensure .md extension
        if not rel_path.endswith(".md"):
            rel_path += ".md"

        full_path = self.vault_path / rel_path

        # Path traversal check: resolve symlinks + ".." components and verify
        # the resulting absolute path is still within the vault directory.
        vault_resolved = self.vault_path.resolve()
        try:
            full_resolved = full_path.resolve()
        except (OSError, ValueError) as e:
            raise ValueError(f"Invalid path: {rel_path}") from e

        if not str(full_resolved).startswith(str(vault_resolved) + "/"):
            logger.warning(f"Path traversal attempt blocked: {rel_path!r} → {full_resolved}")
            raise ValueError(
                f"Path traversal detected: '{rel_path}' resolves outside vault"
            )

        full_resolved.parent.mkdir(parents=True, exist_ok=True)

        # Add frontmatter if tags provided and file is new
        if tags and not full_resolved.exists():
            tag_str = ", ".join(tags)
            content = f"---\ntags: [{tag_str}]\n---\n{content}"

        full_resolved.write_text(content, encoding="utf-8")
        # Return path relative to vault root
        rel_result = str(full_resolved.relative_to(vault_resolved))
        logger.debug(f"Note written: {rel_result}")
        return rel_result
