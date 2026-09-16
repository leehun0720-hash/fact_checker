#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_text.py — 검증 대상 문서를 마크다운 텍스트로 변환

0단계(문서 확보)에서 실행한다. PDF / DOCX / HWPX / MD / TXT를 한 개의
마크다운 파일로 바꾸고, 페이지·표 위치를 표식으로 남겨 뒤 단계의 '위치'
표기에 쓸 수 있게 한다.

사용법:
    python extract_text.py <입력파일> --out /tmp/work/document.md
    python extract_text.py <입력파일> --json      # 메타데이터(페이지 수, 글자 수, 상태)만 출력

의존: pdfplumber(PDF), python-docx(DOCX). HWPX는 표준 라이브러리만 사용.
      Claude API 코드 실행 컨테이너에는 위 라이브러리가 사전 설치되어 있다.
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def _table_to_md(rows):
    rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in rows if r]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def extract_pdf(path: Path):
    import pdfplumber  # 사전 설치

    parts, pages = [], 0
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            pages = i
            parts.append(f"\n\n<!-- page {i} -->\n")
            text = page.extract_text() or ""
            parts.append(text)
            try:
                tables = page.extract_tables() or []
            except Exception:  # 표 추출 실패는 본문 추출을 막지 않는다
                tables = []
            for t_idx, tbl in enumerate(tables, start=1):
                md = _table_to_md(tbl)
                if md:
                    parts.append(f"\n\n<!-- table p{i}-{t_idx} -->\n{md}\n")
    return "".join(parts), pages


def extract_docx(path: Path):
    import docx  # python-docx, 사전 설치
    from docx.document import Document as _Doc
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))
    parts, t_idx = [], 0
    # 문서 본문 순서를 유지하기 위해 body 자식 요소를 순회
    for child in d.element.body.iterchildren():
        if child.tag == qn("w:p"):
            p = Paragraph(child, d)
            style = (p.style.name or "").lower() if p.style is not None else ""
            text = p.text.strip()
            if not text:
                continue
            m = re.match(r"heading (\d)", style)
            if m:
                parts.append("\n" + "#" * int(m.group(1)) + " " + text + "\n")
            else:
                parts.append(text + "\n")
        elif child.tag == qn("w:tbl"):
            t_idx += 1
            tbl = Table(child, d)
            rows = [[c.text for c in r.cells] for r in tbl.rows]
            md = _table_to_md(rows)
            if md:
                parts.append(f"\n<!-- table {t_idx} -->\n{md}\n\n")
    return "".join(parts), None


def extract_hwpx(path: Path):
    """HWPX = OWPML(zip). Contents/section*.xml 의 <hp:p>/<hp:t>/<hp:tbl>을 순서대로 읽는다."""
    parts, t_idx = [], 0
    with zipfile.ZipFile(str(path)) as z:
        sections = sorted(
            [n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)],
            key=lambda n: int(re.search(r"section(\d+)", n).group(1)),
        )
        if not sections:
            return "", None
        for s_idx, name in enumerate(sections, start=1):
            root = ET.fromstring(z.read(name))
            parts.append(f"\n\n<!-- section {s_idx} -->\n")

            def local(tag):
                return tag.rsplit("}", 1)[-1]

            def para_text(p_el):
                # 표 안의 문단은 표 처리에서 다루므로 직계 run의 t만 모은다
                buf = []
                for el in p_el.iter():
                    if local(el.tag) == "t" and el.text:
                        buf.append(el.text)
                return "".join(buf).strip()

            def walk(el):
                nonlocal t_idx
                for ch in list(el):
                    tag = local(ch.tag)
                    if tag == "tbl":
                        t_idx += 1
                        rows = {}
                        for tc in ch.iter():
                            if local(tc.tag) != "tc":
                                continue
                            addr = next((a for a in tc.iter() if local(a.tag) == "cellAddr"), None)
                            r = int(addr.get("rowAddr", 0)) if addr is not None else len(rows)
                            c = int(addr.get("colAddr", 0)) if addr is not None else 0
                            cell_txt = " ".join(
                                para_text(p) for p in tc.iter() if local(p.tag) == "p"
                            ).strip()
                            rows.setdefault(r, {})[c] = cell_txt
                        grid = [
                            [rows[r].get(c, "") for c in range(max(rows[r]) + 1)]
                            for r in sorted(rows)
                        ] if rows else []
                        md = _table_to_md(grid)
                        if md:
                            parts.append(f"\n<!-- table {t_idx} -->\n{md}\n\n")
                    elif tag == "p":
                        # 표 안 문단은 tbl 분기에서 처리됨. 여기서는 표를 품지 않은 문단만.
                        if any(local(x.tag) == "tbl" for x in ch.iter()):
                            walk(ch)
                        else:
                            txt = para_text(ch)
                            if txt:
                                parts.append(txt + "\n")
                    else:
                        walk(ch)

            walk(root)
    return "".join(parts), None


def extract_plain(path: Path):
    return path.read_text(encoding="utf-8", errors="replace"), None


EXTRACTORS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".hwpx": extract_hwpx,
    ".md": extract_plain,
    ".markdown": extract_plain,
    ".txt": extract_plain,
}


def extract(path: Path):
    ext = path.suffix.lower()
    if ext not in EXTRACTORS:
        raise SystemExit(f"지원하지 않는 형식: {ext} (지원: {', '.join(EXTRACTORS)})")
    text, pages = EXTRACTORS[ext](path)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"
    visible = re.sub(r"<!--.*?-->", "", text)
    chars = len(re.sub(r"\s", "", visible))
    if chars == 0:
        status = "failed"
    elif pages and chars / pages < 80:  # 페이지당 80자 미만이면 스캔 PDF 가능성
        status = "partial"
    else:
        status = "ok"
    return text, {"name": path.name, "format": ext.lstrip("."), "pages": pages, "chars": chars, "extraction": status}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out", help="마크다운 출력 경로 (생략하면 stdout)")
    ap.add_argument("--json", action="store_true", help="메타데이터만 JSON으로 출력")
    a = ap.parse_args()

    text, meta = extract(Path(a.path))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text, encoding="utf-8")
        meta["out"] = a.out
    if a.json or a.out:
        print(json.dumps(meta, ensure_ascii=False))
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
