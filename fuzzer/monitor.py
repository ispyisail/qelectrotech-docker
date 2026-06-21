"""
Process monitor: detects crashes, captures ASAN/TSan/Valgrind output,
takes screenshots on crash, and writes structured crash records.
"""
import json
import logging
import os
import re
import signal
import subprocess
import time

log = logging.getLogger(__name__)

_ASAN_HEADLINE = re.compile(
    r"=+\d+=+\s+ERROR:\s+(AddressSanitizer|LeakSanitizer|ThreadSanitizer|UndefinedBehaviorSanitizer)"
    r":\s+(.+)"
)
_ASAN_STACK_LINE = re.compile(r"^\s+#\d+\s+0x[0-9a-f]+\s+in\s+(\S+)")


class CrashRecord:
    def __init__(self, kind: str, message: str, backtrace: list[str], raw: str):
        self.kind = kind
        self.message = message
        self.backtrace = backtrace
        self.raw = raw
        self.timestamp = time.time()

    def key(self) -> str:
        """Dedup key: top 5 unique backtrace frames."""
        top = self.backtrace[:5]
        return "|".join(top)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "kind": self.kind,
            "message": self.message,
            "backtrace": self.backtrace,
        }


def parse_sanitizer_output(text: str) -> list[CrashRecord]:
    """Extract crash records from a block of sanitizer stderr output."""
    records = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _ASAN_HEADLINE.search(lines[i])
        if m:
            kind = m.group(1)
            message = m.group(2).strip()
            # Collect backtrace lines until we hit the next headline or blank run
            bt = []
            j = i + 1
            while j < len(lines) and j < i + 80:
                bm = _ASAN_STACK_LINE.match(lines[j])
                if bm:
                    bt.append(bm.group(1))
                j += 1
            records.append(CrashRecord(kind, message, bt, "\n".join(lines[i:j])))
            i = j
        else:
            i += 1
    return records


def take_screenshot(display: str, path: str) -> bool:
    """Use scrot or import (ImageMagick) to capture the virtual display."""
    env = dict(os.environ, DISPLAY=display)
    for cmd in [
        ["scrot", "-z", path],
        ["import", "-window", "root", path],
    ]:
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=5, env=env)
            if r.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


class ProcessMonitor:
    """
    Watches the QElectroTech subprocess.
    Call `update()` regularly to poll for crashes/sanitizer output.
    """

    def __init__(
        self,
        proc: subprocess.Popen,
        crash_log_path: str,
        screenshot_dir: str,
        display: str = ":99",
    ):
        self.proc = proc
        self.crash_log_path = crash_log_path
        self.screenshot_dir = screenshot_dir
        self.display = display
        self._stderr_buf: list[str] = []
        self._crash_count = 0
        self._seen_keys: set[str] = set()

        os.makedirs(screenshot_dir, exist_ok=True)

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def returncode(self) -> int | None:
        return self.proc.returncode

    def collect_stderr(self):
        """Non-blocking drain of stderr into internal buffer."""
        if self.proc.stderr:
            import select
            while True:
                r, _, _ = select.select([self.proc.stderr], [], [], 0)
                if not r:
                    break
                line = self.proc.stderr.readline()
                if not line:
                    break
                line = line.rstrip("\n")
                self._stderr_buf.append(line)
                if len(self._stderr_buf) > 50_000:
                    self._stderr_buf = self._stderr_buf[-40_000:]

    def flush_and_parse(self) -> list[CrashRecord]:
        """Parse buffered stderr for sanitizer reports."""
        text = "\n".join(self._stderr_buf)
        records = parse_sanitizer_output(text)
        self._stderr_buf.clear()
        return records

    def handle_crash(self, records: list[CrashRecord], action_name: str = ""):
        """Write crash records to the crash log and take a screenshot."""
        self._crash_count += 1
        ts = int(time.time())
        screenshot = os.path.join(self.screenshot_dir, f"crash_{ts}.png")
        took = take_screenshot(self.display, screenshot)

        new_records = []
        for rec in records:
            k = rec.key()
            if k not in self._seen_keys:
                self._seen_keys.add(k)
                new_records.append(rec)
            else:
                log.debug("duplicate crash, suppressing: %s", rec.message[:80])

        entry = {
            "crash_id": self._crash_count,
            "timestamp": ts,
            "action": action_name,
            "screenshot": screenshot if took else None,
            "records": [r.to_dict() for r in new_records],
            "returncode": self.proc.returncode,
        }
        with open(self.crash_log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        for rec in new_records:
            log.error("CRASH [%s] %s: %s", rec.kind, action_name, rec.message)

        return new_records

    def check(self, action_name: str = "") -> bool:
        """
        Collect stderr and check for problems.
        Returns True if a crash/sanitizer event was detected.
        """
        self.collect_stderr()

        if not self.is_alive():
            rc = self.returncode()
            log.warning("QET process exited with rc=%s during %s", rc, action_name)
            remaining_text = ""
            if self.proc.stderr:
                remaining_text = self.proc.stderr.read() or ""
            self._stderr_buf.extend(remaining_text.splitlines())
            records = self.flush_and_parse()
            if not records:
                # Signal crash without sanitizer output
                dummy = CrashRecord(
                    "ProcessCrash",
                    f"exit code {rc}",
                    [],
                    f"Process exited: rc={rc}",
                )
                records = [dummy]
            self.handle_crash(records, action_name)
            return True

        records = self.flush_and_parse()
        if records:
            self.handle_crash(records, action_name)
            return True

        return False

    def kill(self):
        if self.is_alive():
            try:
                self.proc.send_signal(signal.SIGTERM)
                self.proc.wait(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                self.proc.kill()
