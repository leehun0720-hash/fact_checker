"""Claude API 오케스트레이션.

한 작업(job)당 한 번의 에이전트 실행이다:
  파일 업로드(Files API) → Messages 스트리밍(커스텀 스킬 + code_execution + web_search + web_fetch)
  → pause_turn이면 이어서 실행 → $OUTPUT_DIR 산출물 다운로드 → result.json 확보.

검증 로직은 전부 스킬 안에 있다. 이 모듈은 실행·복구·기록만 맡는다.
"""
from __future__ import annotations

import json
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import anthropic

from . import lawapi
from . import store
from .config import settings
from .postprocess import extract_json_block
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schema import Job, ToolEvent, Usage

OUTPUT_NAMES = ("result.json", "report.md", "corrected.md", "log.md")


@dataclass
class RunOutcome:
    raw_result: dict
    files: dict[str, bytes] = field(default_factory=dict)  # 파일명 → 내용
    events: list[ToolEvent] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    final_text: str = ""


class VerifierError(RuntimeError):
    pass


def _client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise VerifierError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    # 스트리밍이므로 SDK의 10분 비스트리밍 제한은 걸리지 않는다. HTTP 타임아웃만 넉넉히 준다.
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=1800)


def _upload(client: anthropic.Anthropic, path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix.lower() == ".hwpx":
        mime = "application/octet-stream"
    with path.open("rb") as fh:
        meta = client.files.upload(file=(path.name, fh, mime))
    return meta.id


def _tools() -> list[dict]:
    tools: list[dict] = [
        {"type": settings.code_execution_tool, "name": "code_execution"},
        {"type": settings.web_search_tool, "name": "web_search", "max_uses": settings.web_search_max_uses},
        {"type": settings.web_fetch_tool, "name": "web_fetch", "max_uses": settings.web_fetch_max_uses,
         "max_content_tokens": 30000},
    ]
    if settings.law_api_oc:
        tools += lawapi.TOOL_DEFINITIONS  # 클라이언트 도구 — 백엔드가 실행해 결과를 돌려준다
    return tools


def _run_client_tools(msg, job: Job, outcome: "RunOutcome", on_progress) -> list[dict]:
    """모델이 호출한 클라이언트 도구(법령 API)를 실행해 tool_result 블록 목록을 만든다."""
    results: list[dict] = []
    for block in msg.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        inp = block.input if isinstance(block.input, dict) else {}
        if block.name in lawapi.TOOL_NAMES:
            if job.counters.get("law_api", 0) >= settings.law_tool_max_calls:
                text, is_err = json.dumps({"error": "법령 API 호출 상한에 도달했습니다. 남은 법령 확인은 web_search로 진행하세요."}, ensure_ascii=False), True
            else:
                text, is_err = lawapi.execute_tool(block.name, inp, settings.law_api_oc)
            job.counters["law_api"] = job.counters.get("law_api", 0) + 1
            detail = f"{block.name} {json.dumps(inp, ensure_ascii=False)}"
        else:
            text, is_err = json.dumps({"error": f"알 수 없는 도구 {block.name}"}, ensure_ascii=False), True
            detail = f"{block.name} (unknown)"
        # 호출 자체는 스트리밍 단계에서 이미 기록됐다. 여기서는 결과 요약만 남긴다.
        try:
            summary = json.loads(text)
            brief = summary.get("error") or (
                f"exists={summary.get('exists')} {summary.get('law_name') or ''} {summary.get('heading') or ''}".strip()
                if "exists" in summary else f"total={summary.get('total')}")
        except Exception:
            brief = text[:120]
        outcome.events.append(ToolEvent(at=Job.now(), tool="law_api_result", detail=f"{detail[:120]} → {brief}"[:300]))
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_err})
    on_progress(job)
    return results


def _skills() -> list[dict]:
    if not settings.dfc_skill_id:
        raise VerifierError("DFC_SKILL_ID가 없습니다. scripts/upload_skill.py 를 먼저 실행하세요.")
    return [{"type": "custom", "skill_id": settings.dfc_skill_id, "version": settings.dfc_skill_version}]


def _describe_block(block) -> tuple[str, str] | None:
    """server_tool_use 블록을 (도구, 한 줄 설명)으로 요약한다. 진행 상태 표시와 검증 로그에 쓴다."""
    btype = getattr(block, "type", None)
    if btype == "tool_use":
        inp = block.input if isinstance(block.input, dict) else {}
        return "law_api", f"{block.name} {json.dumps(inp, ensure_ascii=False)}"[:300]
    if btype != "server_tool_use":
        return None
    name = block.name
    inp = block.input if isinstance(block.input, dict) else {}
    if name == "web_search":
        return "web_search", str(inp.get("query", ""))
    if name == "web_fetch":
        return "web_fetch", str(inp.get("url", ""))
    if name == "bash_code_execution":
        cmd = str(inp.get("command", "")).strip().replace("\n", " ")
        return "bash", cmd[:300]
    if name == "text_editor_code_execution":
        return "editor", f"{inp.get('command', '')} {inp.get('path', '')}".strip()
    if name == "code_execution":  # code_execution_20260521: 파이썬 코드를 직접 실행하는 블록
        code = str(inp.get("code", "")).strip().replace(chr(10), " ⏎ ")
        return "python", code[:300]
    return name, json.dumps(inp, ensure_ascii=False)[:200]


def _file_ids(message) -> list[str]:
    """도구 결과 블록에 담긴 산출물 file_id를 모두 모은다.
    bash_code_execution / code_execution(python) / text_editor 결과 구조가 조금씩 달라 형태에 의존하지 않고 훑는다."""
    ids: list[str] = []
    for item in message.content:
        if not str(getattr(item, "type", "")).endswith("_tool_result"):
            continue
        content = getattr(item, "content", None)
        outputs = getattr(content, "content", None) or []
        for out in outputs if isinstance(outputs, list) else []:
            fid = getattr(out, "file_id", None)
            if fid:
                ids.append(fid)
    return ids


def run_verification(job: Job, on_progress: Callable[[Job], None]) -> RunOutcome:
    client = _client()
    updir = store.uploads_dir(job.org_id, job.id)

    # 1) 업로드
    job.status = "uploading"
    on_progress(job)
    main_id = _upload(client, updir / job.filename)
    extra_ids = [_upload(client, updir / name) for name in job.extra_files]

    # 2) 요청 구성
    content = [
        {"type": "text", "text": build_user_prompt(
            job.options, job.filename, job.extra_files,
            (settings.web_search_max_uses, settings.web_fetch_max_uses),
            law_tools=bool(settings.law_api_oc))},
        {"type": "container_upload", "file_id": main_id},
        *[{"type": "container_upload", "file_id": fid} for fid in extra_ids],
    ]
    messages: list[dict] = [{"role": "user", "content": content}]
    container: dict = {"skills": _skills()}

    outcome = RunOutcome(raw_result={})
    usage = outcome.usage
    counters = job.counters
    all_file_ids: list[str] = []
    job.status = "running"
    job.model = settings.claude_model
    on_progress(job)

    # 3) 실행 — pause_turn / max_tokens 이어가기
    for round_no in range(1, settings.pause_turn_max_rounds + 1):
        usage.rounds = round_no
        seen_blocks = 0
        with client.messages.stream(
            model=settings.claude_model,
            max_tokens=settings.max_tokens,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=_tools(),
            container=container,
        ) as stream:
            for event in stream:
                if event.type == "content_block_stop":
                    snap = stream.current_message_snapshot
                    # 지금 막 끝난 블록만 요약해 진행 상태에 기록
                    while seen_blocks < len(snap.content):
                        desc = _describe_block(snap.content[seen_blocks])
                        seen_blocks += 1
                        if desc:
                            tool, detail = desc
                            if tool == "python":
                                counters["python"] = counters.get("python", 0) + 1
                            else:
                                counters[tool] = counters.get(tool, 0) + 1
                                if tool == "bash" and "python" in detail:
                                    counters["python"] = counters.get("python", 0) + 1
                            ev = ToolEvent(at=Job.now(), tool=tool, detail=detail)
                            outcome.events.append(ev)
                            job.progress.append(ev)
                            if len(job.progress) > 60:  # 화면용은 최근 60개만
                                job.progress = job.progress[-60:]
                            on_progress(job)
            msg = stream.get_final_message()

        usage.input_tokens += msg.usage.input_tokens
        usage.output_tokens += msg.usage.output_tokens
        if msg.usage.server_tool_use:
            usage.web_search_requests += msg.usage.server_tool_use.web_search_requests
            usage.web_fetch_requests += msg.usage.server_tool_use.web_fetch_requests
        all_file_ids += _file_ids(msg)
        if msg.container is not None:
            container = {"id": msg.container.id, "skills": _skills()}

        if msg.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": msg.content})
            continue
        if msg.stop_reason == "tool_use":
            # 클라이언트 도구(법령 API) 호출 — 실행 결과를 돌려주고 같은 컨테이너에서 이어간다
            tool_results = _run_client_tools(msg, job, outcome, on_progress)
            if not tool_results:
                raise VerifierError("tool_use 정지 이유인데 실행할 클라이언트 도구 블록이 없습니다.")
            messages.append({"role": "assistant", "content": msg.content})
            messages.append({"role": "user", "content": tool_results})
            continue
        if msg.stop_reason == "max_tokens":
            # 한 번만 이어서 산출물 내보내기까지 마무리하게 한다
            messages.append({"role": "assistant", "content": msg.content})
            messages.append({"role": "user", "content":
                             "출력 한도에 걸렸다. 남은 작업을 마무리하고 result.json과 report.md를 $OUTPUT_DIR로 내보낸 뒤 <result_json> 블록으로 끝내라."})
            if round_no >= 2:
                break
            continue
        outcome.final_text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        break
    else:
        raise VerifierError(f"{settings.pause_turn_max_rounds}회 이어가기 후에도 완료되지 않았습니다.")

    # 4) 산출물 다운로드
    job.status = "postprocessing"
    on_progress(job)
    for fid in dict.fromkeys(all_file_ids):  # 순서 유지 중복 제거
        try:
            meta = client.files.retrieve_metadata(fid)
            name = Path(meta.filename or fid).name
            data = client.files.download(fid).read()
        except Exception as exc:  # 파일 하나가 실패해도 나머지는 살린다
            outcome.events.append(ToolEvent(at=Job.now(), tool="download_error", detail=f"{fid}: {exc}"))
            continue
        outcome.files[name] = data  # 같은 이름이면 마지막(최신) 것이 남는다

    # 5) result.json 확보 — 파일 → 텍스트 응답 순으로 시도
    raw = None
    if "result.json" in outcome.files:
        try:
            raw = json.loads(outcome.files["result.json"].decode("utf-8"))
        except json.JSONDecodeError:
            raw = None
    if raw is None and outcome.final_text:
        raw = extract_json_block(outcome.final_text)
    if raw is None:
        raise VerifierError("result.json을 받지 못했습니다. (파일 전달·텍스트 블록 모두 실패) 실행 로그를 확인하세요.")
    outcome.raw_result = raw
    return outcome
