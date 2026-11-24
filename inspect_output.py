"""Run inside the task container to reopen a declared deliverable."""
import csv
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

OFFICE = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml",
          ".pptx": "ppt/presentation.xml"}


def inspect(path):
    file = Path(path)
    if file.is_symlink():
        raise ValueError("symlinks are excluded from graded deliverables")
    size = file.stat().st_size
    if not file.is_file() or not size:
        raise ValueError("missing or empty file")
    suffix = file.suffix.lower()
    detail = "nonempty file"
    if suffix in OFFICE or suffix == ".zip":
        with zipfile.ZipFile(file) as archive:
            if not archive.infolist():
                raise ValueError("empty archive")
            if suffix in OFFICE:
                for member in ("[Content_Types].xml", OFFICE[suffix]):
                    with archive.open(member) as xml:
                        ElementTree.parse(xml)
            bad = archive.testzip()
            if bad:
                raise ValueError("bad CRC in " + bad)
            detail = f"opened archive with {len(archive.infolist())} members"
    elif suffix == ".json":
        with file.open(encoding="utf-8-sig") as src:
            json.load(src)
        detail = "parsed JSON"
    elif suffix == ".csv":
        with file.open(encoding="utf-8-sig", newline="") as src:
            if not any(any(cell.strip() for cell in row) for row in csv.reader(src)):
                raise ValueError("empty CSV")
        detail = "read CSV row"
    elif suffix == ".pdf":
        with file.open("rb") as src:
            start = src.read(1024)
            src.seek(max(0, size - 2048))
            if b"%PDF-" not in start or b"%%EOF" not in src.read():
                raise ValueError("missing PDF header or end marker")
        detail = "PDF header and end marker present"
    elif suffix == ".ifc":
        with file.open("rb") as src:
            start = src.read(8192)
            src.seek(max(0, size - 8192))
            if b"ISO-10303-21;" not in start or b"END-ISO-10303-21;" not in src.read():
                raise ValueError("missing STEP envelope")
        detail = "IFC STEP envelope present; geometry requires independent inspection"
    return {"path": path, "bytes": size, "check": detail}


if __name__ == "__main__":
    failed = False
    for item in sys.argv[1:]:
        try:
            print(json.dumps(inspect(item)))
        except Exception as err:
            print(json.dumps({"path": item, "error": str(err)}))
            failed = True
    sys.exit(int(failed))
