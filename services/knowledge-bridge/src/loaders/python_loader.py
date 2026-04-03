"""
Python loader — .py files with AST-based docstring and signature extraction.
"""
import ast
from pathlib import Path
from loguru import logger

from .base import BaseLoader, DocumentEntry


class PythonLoader(BaseLoader):
    extensions = [".py"]
    doc_type = "python"

    def load(self, file_path: Path, rel_path: str, source_name: str) -> DocumentEntry | None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug(f"Cannot read {rel_path}: {e}")
            return None

        stat = file_path.stat()
        title = Path(rel_path).stem
        tags = ["python"]
        metadata: dict = {"functions": [], "classes": [], "imports": []}
        body_parts = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fall back to raw content if unparseable
            return DocumentEntry(
                path=rel_path, source_name=source_name, title=title,
                doc_type=self.doc_type, tags=tags, metadata=metadata,
                word_count=len(content.split()), modified_at=stat.st_mtime,
                content=content, body=content,
            )

        # Module docstring
        module_doc = ast.get_docstring(tree)
        if module_doc:
            body_parts.append(module_doc)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                metadata["classes"].append(node.name)
                tags.append(f"class:{node.name}")
                doc = ast.get_docstring(node)
                if doc:
                    body_parts.append(f"class {node.name}: {doc}")
                else:
                    body_parts.append(f"class {node.name}")

            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Build signature
                args = []
                for arg in node.args.args:
                    if arg.arg != "self":
                        args.append(arg.arg)
                sig = f"def {node.name}({', '.join(args)})"
                metadata["functions"].append(node.name)
                doc = ast.get_docstring(node)
                if doc:
                    body_parts.append(f"{sig}: {doc}")
                else:
                    body_parts.append(sig)

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    metadata["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    metadata["imports"].append(node.module)

        body = "\n".join(body_parts) if body_parts else content

        return DocumentEntry(
            path=rel_path, source_name=source_name, title=title,
            doc_type=self.doc_type, tags=tags, metadata=metadata,
            word_count=len(body.split()), modified_at=stat.st_mtime,
            content=content, body=body,
        )
