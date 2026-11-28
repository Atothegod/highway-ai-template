#!/usr/bin/env python3
"""Send one synthetic BEM incident per user in a synchronized burst."""

import argparse
import csv
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
import math
from pathlib import Path
import re
from threading import Barrier
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from vm_metrics import VmMonitor, snapshot


SCENARIOS = (
    ("สุขุมวิท", "เครื่องอ่านบัตรแสดงข้อผิดพลาดทั้งที่ลองแตะบัตรใหม่แล้ว", "ประตูทางเข้า"),
    ("สีลม", "พื้นเปียกหลังฝนตกและยังไม่มีป้ายเตือน", "ทางเดินเชื่อม"),
    ("สามย่าน", "บันไดเลื่อนหยุดและผู้โดยสารต้องอ้อมไปอีกด้าน", "ทางเชื่อมชั้นจำหน่ายบัตร"),
    ("ห้วยขวาง", "ป้ายบอกทางมองเห็นยากเพราะไฟดับบางส่วน", "โถงทางออก"),
    ("พระราม 9", "กดปุ่มเรียกลิฟต์แล้วประตูไม่เปิดแม้รออยู่หลายนาที", "หน้าลิฟต์"),
    ("บางซื่อ", "ตู้จำหน่ายบัตรค้างอยู่ที่หน้าชำระเงิน", "โถงจำหน่ายบัตร"),
    ("เตาปูน", "เสียงประกาศเบามากจนฟังข้อมูลขบวนถัดไปไม่ชัด", "ชานชาลา"),
    ("ลาดพร้าว", "มีขยะตกค้างกีดขวางทางเดินบางส่วน", "ทางเดินใกล้ทางออก"),
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def article(index, username):
    station, incident, location = SCENARIOS[(index - 1) % len(SCENARIOS)]
    hour, minute = divmod(7 * 60 + index - 1, 60)
    return (
        f"[ข้อมูลสมมติสำหรับทดสอบระบบ {username}]\n"
        f"วันนี้เวลาประมาณ {hour % 24:02d}:{minute:02d} น. ผมเดินทางผ่านสถานี MRT{station} "
        f"และพบว่า{incident} บริเวณ{location} จึงอยากแจ้งให้เจ้าหน้าที่ทราบครับ\n"
        "ช่วงที่ผมผ่านมีผู้โดยสารใช้งานบริเวณดังกล่าวอยู่หลายคน "
        "ผมย้ายไปใช้เส้นทางอื่นและเดินทางต่อได้ อยากให้ทีมงานช่วยตรวจสอบจุดนี้ "
        "และแจ้งด้วยว่าต้องระบุข้อมูลอะไรเพิ่มเติมเพื่อให้ติดตามเรื่องได้ครับ"
    )


def request(opener, base_url, path, timeout, data=None, headers=None):
    req = Request(base_url + path, data=data, headers=headers or {})
    try:
        response = opener.open(req, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        return response.code, response.headers, response.read().decode("utf-8", errors="replace")


def prepare(row, base_url, timeout):
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies), NoRedirect())
    stage = "GET /login/"
    try:
        status, _, _ = request(opener, base_url, "/login/", timeout)
        row["http_status"] = status
        if status != 200:
            raise ValueError(f"expected HTTP 200, received HTTP {status}")
        csrf = next((cookie for cookie in cookies if cookie.name == "csrftoken"), None)
        if csrf is None:
            raise ValueError("response did not set csrftoken")
        if csrf.secure and urlsplit(base_url).scheme == "http":
            raise ValueError(
                "Django set a Secure CSRF cookie over HTTP. Use the test deployment's HTTPS "
                "origin or start the local test backend with DJANGO_HTTPS_DOMAIN empty."
            )

        form = urlencode({
            "username": row["user_id"], "pdpa_consent": "on", "csrfmiddlewaretoken": csrf.value,
        }).encode()
        stage = "POST /login/"
        row["http_status"] = ""
        status, headers, _ = request(
            opener, base_url, "/login/", timeout, form,
            {"Content-Type": "application/x-www-form-urlencoded", "Referer": base_url + "/login/"},
        )
        row["http_status"] = status
        if status == 403:
            raise ValueError("HTTP 403 during login. Check Django CSRF settings and proxy scheme.")
        if status != 302 or urlsplit(headers.get("Location", "")).path != "/chat/":
            raise ValueError(f"expected HTTP 302 to /chat/, received HTTP {status}")
        session = next((cookie for cookie in cookies if cookie.name == "sessionid"), None)
        if session is None:
            raise ValueError("response did not set sessionid")
        if session.secure and urlsplit(base_url).scheme == "http":
            raise ValueError("Django set a Secure session cookie. Use the test deployment's HTTPS origin.")
        csrf = next((cookie.value for cookie in cookies if cookie.name == "csrftoken"), "")
        if not csrf:
            raise ValueError("No csrftoken after login")
    except (OSError, URLError, ValueError) as error:
        row.update(state="login_failed", error=f"{stage}: {error}")
        return None
    row["http_status"] = ""
    return opener, csrf


def send(row, session, gate, base_url, timeout):
    opener, csrf = session
    body = json.dumps({"message": row["article"]}, ensure_ascii=False).encode()
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-CSRFToken": csrf,
        "Referer": base_url + "/chat/",
    }
    gate.wait()
    started = perf_counter()
    row["sent_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    try:
        status, _, response = request(opener, base_url, "/api/chat/", timeout, body, headers)
        row["http_status"] = status
        row["latency_ms"] = round((perf_counter() - started) * 1000, 2)
        try:
            payload = json.loads(response)
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        case = payload.get("case")
        if not isinstance(case, dict):
            case = {}
        row.update(
            reply=payload.get("reply") or "",
            ticket_id=case.get("ticket_id", ""),
            flow_state=case.get("flow_state", ""),
        )
        if status == 200 and row["reply"]:
            row["state"] = "ok"
        else:
            row.update(
                state="chat_failed",
                error=payload.get("error") or (
                    "Agent response has no reply" if status == 200 else f"HTTP {status}"
                ),
            )
    except (OSError, URLError, ValueError) as error:
        row.update(state="chat_failed", error=str(error),
                   latency_ms=round((perf_counter() - started) * 1000, 2))


def csv_row(row):
    # Keep agent-provided text from being evaluated as a spreadsheet formula.
    return {
        key: "'" + value if isinstance(value, str) and (
            re.match(r"^\s*[=+@-]", value) or value.startswith(("\t", "\r", "\n"))
        ) else value
        for key, value in row.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Origin of the test deployment")
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=120, help="HTTP socket timeout in seconds")
    parser.add_argument("--output", type=Path, default=Path("load-chat-results.csv"))
    parser.add_argument("--vm-metrics", action="store_true", help="Collect resources on this Linux VM")
    parser.add_argument("--p95-limit-ms", type=float, help="Optional p95 latency target in milliseconds")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    origin = urlsplit(base_url)
    if (origin.scheme not in ("https", "http") or not origin.hostname
            or origin.path or origin.query or origin.fragment or origin.username is not None):
        parser.error("--base-url must be an HTTP(S) origin without a path or credentials")
    if args.users < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--users and --timeout must be positive")
    summary_path = args.output.with_suffix(".summary.txt")
    metrics_path = args.output.with_suffix(".vm.csv")
    for path in [args.output, summary_path] + ([metrics_path] if args.vm_metrics else []):
        if path.exists():
            parser.error(f"{path} already exists; choose a new output file")
    if args.p95_limit_ms is not None and (
        not math.isfinite(args.p95_limit_ms) or args.p95_limit_ms <= 0
    ):
        parser.error("--p95-limit-ms must be positive")
    monitor = None
    if args.vm_metrics:
        try:
            snapshot()
        except (OSError, ValueError, KeyError) as error:
            parser.error(f"--vm-metrics requires Linux host /proc counters ({error})")
    if args.output == summary_path or (args.vm_metrics and args.output == metrics_path):
        parser.error("--output must differ from the generated report paths")

    run_started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    burst_seconds = None
    run_id = uuid4().hex[:10]
    rows = []
    for index in range(1, args.users + 1):
        user_id = f"load-{run_id}-{index:03d}"
        rows.append(dict(
            user_id=user_id, article=article(index, user_id), reply="", state="",
            http_status="", latency_ms="", sent_at_utc="", ticket_id="", flow_state="", error="",
        ))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()

        print(f"Preparing {args.users} sessions...", flush=True)
        with ThreadPoolExecutor(max_workers=min(10, args.users)) as pool:
            sessions = list(pool.map(lambda row: prepare(row, base_url, args.timeout), rows))

        ready = [(row, session) for row, session in zip(rows, sessions) if session is not None]
        print(f"Sending {len(ready)}/{args.users} chat requests in one burst...", flush=True)
        if ready:
            gate = Barrier(len(ready) + 1)
            with ThreadPoolExecutor(max_workers=len(ready)) as pool:
                try:
                    futures = [
                        pool.submit(send, row, session, gate, base_url, args.timeout)
                        for row, session in ready
                    ]
                    if args.vm_metrics:
                        monitor = VmMonitor(snapshot())
                        monitor.thread.start()
                    burst_start = perf_counter()
                    gate.wait()
                    for future in futures:
                        future.result()
                    burst_seconds = perf_counter() - burst_start
                except BaseException:
                    gate.abort()
                    raise
                finally:
                    if monitor is not None:
                        monitor.stop.set()
                        monitor.thread.join()
        writer.writerows(map(csv_row, rows))

    latencies = sorted(row["latency_ms"] for row in rows if row["state"] == "ok")
    states = Counter(row["state"] for row in rows)
    statuses = Counter(row["http_status"] or "no HTTP response" for row in rows if row["sent_at_utc"])
    lines = [
        f"Run: {run_id} | UTC start: {run_started}",
        f"Target: {base_url}",
        f"Users requested: {args.users} | Chat attempts: {len(ready)}",
        f"Successful replies: {len(latencies)}/{args.users} ({len(latencies) / args.users:.1%})",
        f"Login failures: {states['login_failed']} | Chat failures: {states['chat_failed']}",
        f"Chat HTTP statuses: {dict(statuses)}",
    ]
    login_errors = Counter(
        (row["http_status"] or "no HTTP response", row["error"])
        for row in rows if row["state"] == "login_failed"
    )
    for (status, error), count in login_errors.most_common(5):
        lines.append(f"Login diagnosis ({count} users, status {status}): {error}")
    if not ready:
        lines.append("No chat traffic reached the test endpoint. This run cannot assess agent capacity.")
    if burst_seconds is not None:
        lines.append(f"Burst duration: {burst_seconds:.2f} s")
    percentiles = {}
    if latencies:
        for p in (50, 95, 99):
            percentiles[p] = latencies[math.ceil(len(latencies) * p / 100) - 1]
            lines.append(f"Successful reply p{p}: {percentiles[p]:.2f} ms")
    passed = len(latencies) == args.users
    if args.p95_limit_ms is not None:
        passed = passed and percentiles[95] <= args.p95_limit_ms
        lines.append(f"Target: all users receive a reply and p95 ≤ {args.p95_limit_ms:g} ms")
        lines.append(f"Target result: {'PASS' if passed else 'FAIL'}")
    else:
        lines.append("Latency target: unset. Capacity verdict requires an agreed latency target.")
    if monitor is not None:
        monitor.write(metrics_path)
        lines.extend(monitor.summary())
        if monitor.samples:
            lines.append(f"VM metrics CSV: {metrics_path}")
    elif args.vm_metrics:
        lines.append("Host telemetry unavailable because no chat request was sent.")
    lines.append(f"Chat CSV: {args.output}")
    summary = "\n".join(lines)
    with summary_path.open("x", encoding="utf-8") as output:
        output.write(summary + "\n")
    print(summary)
    print(f"Summary saved: {summary_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
