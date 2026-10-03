import hashlib
from pathlib import Path
from typing import Any, cast

import pymupdf

from ..models import LineIndex, PageEvidence


def file_sha256(document: Path) -> str:
    digest = hashlib.sha256()
    with document.open("rb") as pdf:
        for block in iter(lambda: pdf.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def line_index_path(storage_path: Path, doc_id: str) -> Path:
    return storage_path / "line-index" / f"{doc_id}.json"


def build_line_index(
    document: Path, storage_path: Path, doc_id: str, stored_name: str
) -> LineIndex:
    pages: list[PageEvidence] = []
    with pymupdf.open(document) as pdf:
        for offset in range(len(pdf)):
            lines = []
            page_dict = cast(dict[str, Any], pdf[offset].get_text("dict", sort=True))
            for block in page_dict["blocks"]:
                if block.get("type") != 0:
                    continue
                for source_line in block.get("lines", []):
                    text = "".join(
                        span.get("text", "") for span in source_line.get("spans", [])
                    ).strip()
                    if text:
                        lines.append(
                            {
                                "line": len(lines) + 1,
                                "text": text,
                                "bbox": [
                                    round(value, 2) for value in source_line["bbox"]
                                ],
                            }
                        )
            pages.append(PageEvidence(page=offset + 1, lines=lines))
    index = LineIndex(
        doc_id=doc_id,
        name=stored_name,
        source_path=str(document),
        source_sha256=file_sha256(document),
        pages=pages,
    )
    destination = line_index_path(storage_path, doc_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(index.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(destination)
    return index


def load_line_index(storage_path: Path, doc_id: str) -> LineIndex:
    source = line_index_path(storage_path, doc_id)
    if not source.is_file():
        raise ValueError(f"No local line index for {doc_id}. Re-index its PDF first.")
    return LineIndex.model_validate_json(source.read_text(encoding="utf-8"))
