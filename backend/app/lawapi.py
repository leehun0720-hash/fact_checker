"""국가법령정보센터(law.go.kr) 오픈API — Claude 클라이언트 도구.

검증 2e 단계(법령·규정)에서 모델이 호출한다. 웹 검색보다 정확한 이유는 조문 단위로
'현행 조문 원문 + 시행일자'를 기관 원자료에서 직접 받기 때문이다.

- law_search(query)                  → 현행 법령 목록 (법령명, 법령ID, 법령구분, 소관부처, 공포·시행일)
- law_article(law_id, article, ...)  → 특정 조(항·호)의 현행 원문

OC(인증값)는 open.law.go.kr에서 신청한 이메일 아이디. LAW_API_OC 환경변수로 준다.
API 응답 형식은 2026-09 실측 기준(JSON: LawSearch.law[], 법령.기본정보/조문.조문단위).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://www.law.go.kr/DRF"
TIMEOUT = 25

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "law_search",
        "description": (
            "국가법령정보센터(law.go.kr) 오픈API로 현행 법령 목록을 검색한다. 법령명(약칭 포함)으로 검색해 "
            "법령ID·법령구분(법률/대통령령/부령)·소관부처·공포일·시행일을 얻는다. 조문을 조회하려면 먼저 이 도구로 "
            "법령ID를 확보한다. 법률과 시행령·시행규칙은 별개 법령이므로 문서가 인용한 것이 어느 것인지 구분해 고른다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "법령명 또는 키워드 (예: 지능정보화 기본법, 개인정보 보호법 시행령)"},
                "display": {"type": "integer", "description": "최대 결과 수 (기본 5, 최대 20)", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "law_article",
        "description": (
            "국가법령정보센터 오픈API로 특정 법령의 현행 조문 원문을 조회한다. law_search로 얻은 법령ID와 조 번호를 준다. "
            "결과의 조문제목·조문내용·항·호·시행일자를 문서의 인용과 대조한다. 조문이 없으면 exists=false가 온다 — "
            "이는 '해당 조가 현행 법령에 존재하지 않음'이라는 확정 근거다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "law_id": {"type": "string", "description": "법령ID (law_search 결과의 law_id, 예: 000028)"},
                "article": {"type": "string", "description": "조 번호. '14', '제14조', '10의2' 모두 허용"},
                "paragraph": {"type": "string", "description": "항 번호 (선택, 예: '1')"},
                "item": {"type": "string", "description": "호 번호 (선택, 예: '2' 또는 '10의2')"},
            },
            "required": ["law_id", "article"],
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOL_DEFINITIONS}


class LawApiError(RuntimeError):
    pass


def _get(path: str, params: dict[str, Any], oc: str) -> Any:
    params = {"OC": oc, "type": "JSON", **params}
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (DocFactChecker)"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise LawApiError(f"law.go.kr 연결 실패: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 인증값 오류 등은 HTML로 돌아온다
        snippet = re.sub(r"<[^>]+>", " ", raw)[:300].strip()
        raise LawApiError(f"law.go.kr가 JSON이 아닌 응답을 보냈습니다 (OC 인증값 확인): {snippet}")


def _six(num: str) -> str:
    """'14' → 001400, '10의2' → 001002, '제3조' → 000300"""
    m = re.search(r"(\d+)\s*[조항호]?\s*(?:의\s*(\d+))?", str(num))
    if not m:
        raise LawApiError(f"번호를 해석할 수 없습니다: {num!r}")
    main, sub = int(m.group(1)), int(m.group(2) or 0)
    return f"{main:04d}{sub:02d}"


def _as_list(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _clean(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def law_search(oc: str, query: str, display: int = 5) -> dict:
    display = max(1, min(int(display or 5), 20))
    data = _get("lawSearch.do", {"target": "law", "query": query, "display": display}, oc)
    root = data.get("LawSearch", data)
    total = int(root.get("totalCnt", 0) or 0)
    items = []
    for it in _as_list(root.get("law")):
        items.append({
            "law_name": it.get("법령명한글"),
            "abbr": it.get("법령약칭명") or None,
            "law_id": it.get("법령ID"),
            "mst": it.get("법령일련번호"),
            "kind": it.get("법령구분명"),
            "ministry": it.get("소관부처명"),
            "promulgated": it.get("공포일자"),
            "effective": it.get("시행일자"),
            "revision": it.get("제개정구분명"),
            "status": it.get("현행연혁코드"),
        })
    return {"query": query, "total": total, "results": items,
            "source": "국가법령정보센터 오픈API lawSearch(target=law)"}


def _flatten_article(unit: dict) -> str:
    """조문단위 → 사람이 읽는 원문 한 덩어리 (조문내용 + 항/호/목)."""
    parts = [_clean(unit.get("조문내용"))]
    for h in _as_list(unit.get("항")):
        if isinstance(h, dict):
            if h.get("항내용"):
                parts.append(_clean(h["항내용"]))
            for ho in _as_list(h.get("호")):
                if isinstance(ho, dict):
                    if ho.get("호내용"):
                        parts.append(_clean(ho["호내용"]))
                    for mok in _as_list(ho.get("목")):
                        if isinstance(mok, dict) and mok.get("목내용"):
                            parts.append(_clean(mok["목내용"]))
    return "\n".join(p for p in parts if p)


def law_article(oc: str, law_id: str, article: str, paragraph: str | None = None, item: str | None = None) -> dict:
    params: dict[str, Any] = {"target": "lawjosub", "ID": str(law_id).strip(), "JO": _six(article)}
    if paragraph:
        params["HANG"] = _six(paragraph)
    if item:
        params["HO"] = _six(item)
    data = _get("lawService.do", params, oc)
    law = data.get("법령") or {}
    info = law.get("기본정보") or {}
    unit = (law.get("조문") or {}).get("조문단위") if isinstance(law.get("조문"), dict) else None
    base = {
        "law_id": info.get("법령ID") or law_id,
        "law_name": info.get("법령명_한글"),
        "kind": (info.get("법종구분") or {}).get("content") if isinstance(info.get("법종구분"), dict) else info.get("법종구분"),
        "ministry": (info.get("소관부처") or {}).get("content") if isinstance(info.get("소관부처"), dict) else info.get("소관부처"),
        "law_effective": info.get("시행일자"),
        "former_name": info.get("이전법령명") or None,
        "requested_article": str(article),
        "source": "국가법령정보센터 오픈API lawService(target=lawjosub)",
    }
    if not info:
        base["exists"] = False
        base["note"] = "법령ID에 해당하는 법령을 찾지 못했습니다. law_search로 법령ID를 다시 확인하세요."
        return base
    if not unit:
        base["exists"] = False
        base["note"] = "이 법령의 현행 조문에 해당 조가 없습니다. (삭제·이동되었거나 조 번호가 틀렸을 수 있음)"
        return base
    base.update({
        "exists": True,
        "article_no": unit.get("조문번호"),
        "title": unit.get("조문제목"),
        "heading": _clean(unit.get("조문내용")),
        "text": _flatten_article(unit),
        "article_effective": unit.get("조문시행일자"),
        "changed": unit.get("조문변경여부"),
        "moved_from": unit.get("조문이동이전") or None,
    })
    return base


def execute_tool(name: str, inp: dict, oc: str) -> tuple[str, bool]:
    """(결과 텍스트, is_error). 결과는 JSON 문자열 — 모델이 그대로 근거로 인용할 수 있게 원문을 담는다."""
    try:
        if name == "law_search":
            out = law_search(oc, inp.get("query", ""), inp.get("display", 5))
        elif name == "law_article":
            out = law_article(oc, inp.get("law_id", ""), inp.get("article", ""),
                              inp.get("paragraph") or None, inp.get("item") or None)
        else:
            return json.dumps({"error": f"알 수 없는 도구 {name}"}, ensure_ascii=False), True
        return json.dumps(out, ensure_ascii=False), False
    except LawApiError as exc:
        return json.dumps({"error": str(exc), "fallback": "web_search로 law.go.kr을 검색해 확인하고, 판정은 '의심' 이상으로 올리지 않는다."},
                          ensure_ascii=False), True
