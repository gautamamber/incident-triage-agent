import re
from dataclasses import dataclass

import httpx

# Matches a Python traceback frame line: File "<path>", line <n>, in <func>
_FRAME_RE = re.compile(r'File "([^"]+)", line \d+, in (\S+)')
APP_MARKER = "/app/app/"


@dataclass
class LogRecord:
    timestamp_ns: int
    service_name: str
    severity_text: str
    body: str
    exception_type: str | None
    top_frame: str | None
    trace_id: str | None


def _top_app_frame_from_stacktrace(stacktrace: str) -> str | None:
    """The innermost app-code frame, skipping library/site-packages frames.
    A traceback lists frames outermost-first, so the crash site is the LAST
    match, not the first. Without this, every exception caught by a shared
    handler (like our global one in main.py) would report the *handler's*
    location as top_frame instead of where the bug actually is."""
    app_frames = [
        (path, func)
        for path, func in _FRAME_RE.findall(stacktrace)
        if APP_MARKER in path and "site-packages" not in path
    ]
    if not app_frames:
        return None
    path, func = app_frames[-1]
    relative = path.split(APP_MARKER, 1)[1]
    return f"app/{relative}:{func}"


def _parse_streams(streams: list[dict], service: str) -> list[LogRecord]:
    records = []
    for stream in streams:
        s = stream["stream"]
        stacktrace = s.get("exception_stacktrace")
        if stacktrace:
            top_frame = _top_app_frame_from_stacktrace(stacktrace)
        else:
            code_file = s.get("code_file_path")
            code_func = s.get("code_function_name")
            top_frame = f"{code_file}:{code_func}" if code_file and code_func else None
        for ts_str, line in stream["values"]:
            records.append(
                LogRecord(
                    timestamp_ns=int(ts_str),
                    service_name=s.get("service_name", service),
                    severity_text=s.get("severity_text", "ERROR"),
                    body=line,
                    exception_type=s.get("exception_type"),
                    top_frame=top_frame,
                    trace_id=s.get("trace_id"),
                )
            )
    records.sort(key=lambda r: r.timestamp_ns)
    return records


def search_logs(
    loki_url: str,
    service: str,
    start_ns: int,
    end_ns: int,
    level: str | None = None,
    contains: str | None = None,
    limit: int = 200,
) -> list[LogRecord]:
    """General log search for evidence collection (doc section 7.1) — broader
    than the detector's error-only poll: any severity, optional text filter."""
    query = f'{{service_name="{service}"}}'
    if level:
        query += f' | severity_text=~"{level}"'
    if contains:
        escaped = contains.replace('"', '\\"')
        query += f' |= "{escaped}"'

    resp = httpx.get(
        f"{loki_url}/loki/api/v1/query_range",
        params={
            "query": query,
            "start": start_ns,
            "end": end_ns,
            "limit": limit,
            "direction": "forward",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return _parse_streams(resp.json()["data"]["result"], service)


def query_errors(
    loki_url: str, service: str, start_ns: int, end_ns: int, limit: int = 1000
) -> list[LogRecord]:
    """ERROR/FATAL records for `service` in [start_ns, end_ns) — what the
    detector polls every 30s."""
    return search_logs(loki_url, service, start_ns, end_ns, level="ERROR|FATAL", limit=limit)
