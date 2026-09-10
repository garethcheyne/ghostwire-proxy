"""Container OS package and security-update posture.

Answers, per container: what base OS is it, how many packages does it carry,
how many of those have upgrades waiting, are any of them security updates, and
is anything actually applying them.

A note on what "auto security updates" means for a container, because it is not
the same as for a VM. The durable fix for a vulnerable package in a container is
to rebuild the image from a refreshed base and redeploy — an in-container
`apk upgrade` is undone by the next `docker compose up`. So this reports two
different things and does not conflate them:

  * `pending_updates`  — packages with a newer version available *right now* in
    the running container. This is the live exposure.
  * `image_age_days`   — how stale the image itself is. A container with zero
    pending updates but a nine-month-old image is not safe; it just has an
    equally old package index.

Edge containers (anything publishing a port to the internet — in this stack the
proxy) are flagged, because a vulnerable package there is reachable by anyone.
"""
import asyncio
import json
import logging
import re
import shlex
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:  # pragma: no cover
    DOCKER_AVAILABLE = False

# Each exec is capped so one wedged container can't hang a scan of the fleet.
EXEC_TIMEOUT_SECONDS = 25

# Package managers we know how to interrogate, in detection order.
_PACKAGE_MANAGERS = ("apk", "apt-get", "dnf", "yum", "pacman")


class ContainerSecurityScanner:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if not DOCKER_AVAILABLE:
            return None
        if self._client is None:
            try:
                self._client = docker.from_env()
            except Exception as e:
                logger.warning("Could not connect to Docker: %s", e)
                return None
        return self._client

    # ── low-level helpers ────────────────────────────────────────────────

    def _exec(self, container, command: str) -> tuple[int, str]:
        """Run a shell command inside a container. Returns (exit_code, output).

        Errors are returned rather than raised: a container without a shell, or
        one that is stopped, is a normal condition here, not a failure of the
        scan.
        """
        try:
            result = container.exec_run(
                ["/bin/sh", "-c", command],
                stdout=True,
                stderr=True,
                demux=False,
            )
            output = result.output.decode("utf-8", errors="replace") if result.output else ""
            return result.exit_code, output
        except Exception as e:
            return -1, str(e)

    def _detect_os(self, container) -> dict:
        """Read /etc/os-release for distro identity."""
        code, output = self._exec(container, "cat /etc/os-release 2>/dev/null")
        info = {"id": None, "name": None, "version": None, "pretty_name": None}

        if code != 0 or not output:
            return info

        fields = {}
        for line in output.splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip().strip('"')

        info["id"] = fields.get("ID")
        info["name"] = fields.get("NAME")
        info["version"] = fields.get("VERSION_ID")
        info["pretty_name"] = fields.get("PRETTY_NAME") or fields.get("NAME")
        return info

    def _detect_package_manager(self, container) -> Optional[str]:
        checks = " ; ".join(
            f"command -v {pm} >/dev/null 2>&1 && echo {pm}" for pm in _PACKAGE_MANAGERS
        )
        code, output = self._exec(container, checks)
        for line in (output or "").split():
            if line in _PACKAGE_MANAGERS:
                return line
        return None

    # ── package inventory ────────────────────────────────────────────────

    def _installed_packages(self, container, manager: str) -> tuple[int, list[dict]]:
        """Total installed count plus the full list where it's cheap to get."""
        if manager == "apk":
            code, out = self._exec(container, "apk info -v 2>/dev/null")
            if code != 0:
                return 0, []
            packages = []
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Format: name-1.2.3-r4 — split off the last two dash-groups.
                match = re.match(r"^(.*)-([^-]+-r\d+)$", line)
                if match:
                    packages.append({"name": match.group(1), "version": match.group(2)})
                else:
                    packages.append({"name": line, "version": None})
            return len(packages), packages

        if manager == "apt-get":
            code, out = self._exec(
                container,
                "dpkg-query -W -f='${Package}\\t${Version}\\n' 2>/dev/null",
            )
            if code != 0:
                return 0, []
            packages = []
            for line in out.splitlines():
                if "\t" in line:
                    name, _, version = line.partition("\t")
                    packages.append({"name": name.strip(), "version": version.strip()})
            return len(packages), packages

        if manager in ("dnf", "yum"):
            code, out = self._exec(container, "rpm -qa --qf '%{NAME}\\t%{VERSION}-%{RELEASE}\\n' 2>/dev/null")
            if code != 0:
                return 0, []
            packages = []
            for line in out.splitlines():
                if "\t" in line:
                    name, _, version = line.partition("\t")
                    packages.append({"name": name.strip(), "version": version.strip()})
            return len(packages), packages

        return 0, []

    def _pending_updates(self, container, manager: str) -> dict:
        """Packages with a newer version available.

        Refreshes the package index first — without that, a container whose
        index is months old reports "0 updates" while being badly out of date,
        which is the most dangerous possible wrong answer.
        """
        if manager == "apk":
            # `apk upgrade --simulate` lists what would change.
            code, out = self._exec(
                container,
                "apk update >/dev/null 2>&1; apk upgrade --simulate 2>/dev/null",
            )
            if code != 0:
                return {"count": 0, "packages": [], "error": out[:500] or "apk query failed"}

            packages = []
            for line in out.splitlines():
                # "(1/3) Upgrading busybox (1.36.1-r5 -> 1.36.1-r7)"
                match = re.search(r"Upgrading\s+(\S+)\s+\(([^\s]+)\s*->\s*([^)]+)\)", line)
                if match:
                    packages.append({
                        "name": match.group(1),
                        "current_version": match.group(2),
                        "available_version": match.group(3).strip(),
                    })
            return {"count": len(packages), "packages": packages}

        if manager == "apt-get":
            code, out = self._exec(
                container,
                "apt-get update >/dev/null 2>&1; apt-get -s -o Debug::NoLocking=1 upgrade 2>/dev/null",
            )
            if code != 0:
                return {"count": 0, "packages": [], "error": out[:500] or "apt query failed"}

            packages = []
            for line in out.splitlines():
                # "Inst libssl3 [3.0.11-1] (3.0.13-1 Debian-Security:12 [amd64])"
                match = re.match(r"^Inst\s+(\S+)\s+\[([^\]]+)\]\s+\(([^\s]+)\s+(.*)\)", line)
                if match:
                    source = match.group(4)
                    packages.append({
                        "name": match.group(1),
                        "current_version": match.group(2),
                        "available_version": match.group(3),
                        "security": "security" in source.lower(),
                    })
            return {
                "count": len(packages),
                "packages": packages,
                "security_count": sum(1 for p in packages if p.get("security")),
            }

        if manager in ("dnf", "yum"):
            code, out = self._exec(container, f"{manager} -q check-update 2>/dev/null")
            # check-update exits 100 when updates exist — not an error.
            if code not in (0, 100):
                return {"count": 0, "packages": [], "error": out[:500] or f"{manager} query failed"}

            packages = []
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3 and not line.startswith(("Last metadata", "Obsoleting")):
                    packages.append({
                        "name": parts[0],
                        "current_version": None,
                        "available_version": parts[1],
                        "security": "security" in line.lower(),
                    })
            return {
                "count": len(packages),
                "packages": packages,
                "security_count": sum(1 for p in packages if p.get("security")),
            }

        return {"count": 0, "packages": [], "error": f"Unsupported package manager: {manager}"}

    def _auto_update_status(self, container, manager: str) -> dict:
        """Is anything inside the container applying updates on its own?"""
        status = {
            "enabled": False,
            "mechanism": None,
            "detail": None,
        }

        if manager == "apt-get":
            code, out = self._exec(
                container,
                "cat /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null; "
                "command -v unattended-upgrade >/dev/null 2>&1 && echo HAS_UNATTENDED",
            )
            has_binary = "HAS_UNATTENDED" in (out or "")
            periodic = re.search(
                r'APT::Periodic::Unattended-Upgrade\s+"(\d+)"', out or ""
            )
            enabled = bool(has_binary and periodic and periodic.group(1) != "0")
            status.update({
                "enabled": enabled,
                "mechanism": "unattended-upgrades" if has_binary else None,
                "detail": (
                    "unattended-upgrades installed and enabled" if enabled
                    else "unattended-upgrades installed but not enabled" if has_binary
                    else "unattended-upgrades not installed"
                ),
            })
            return status

        if manager == "apk":
            # Alpine ships no auto-updater; the only way it happens is a cron job
            # that actually runs `apk upgrade`. Match on that specifically —
            # merely *having* a crontab proves nothing, since plenty of images
            # schedule unrelated jobs (this proxy's own nginx runs logrotate).
            code, out = self._exec(
                container,
                "grep -rlE 'apk[[:space:]]+(-[^[:space:]]+[[:space:]]+)*upgrade' "
                "/etc/crontabs /etc/periodic /var/spool/cron 2>/dev/null",
            )
            matches = [line for line in (out or "").splitlines() if line.strip()]
            found = bool(matches)
            status.update({
                "enabled": found,
                "mechanism": "cron (apk upgrade)" if found else None,
                "detail": (
                    f"A cron entry runs apk upgrade ({', '.join(matches[:3])})" if found
                    else "Alpine has no automatic updater; rebuild the image to pick up fixes"
                ),
            })
            return status

        status["detail"] = "No automatic update mechanism detected"
        return status

    def _stale_process_count(self, container) -> Optional[int]:
        """How many running processes still map libraries that have been
        replaced on disk.

        This is the difference between "patched" and "protected". Upgrading a
        package rewrites the file; every process that already had the old copy
        mapped keeps using it until it restarts, so a container can report zero
        pending updates while still executing the vulnerable code.

        Only real on-disk files count. A plain grep for "(deleted)" is wrong:
        nginx's shared-memory zones show up as `/dev/zero (deleted)` from the
        moment it starts, so every freshly restarted container would look like
        it needed restarting again — an endless restart loop. Anonymous and
        pseudo-file mappings are therefore excluded, leaving only paths that
        a package manager could actually have replaced.

        Returns None when it cannot be determined (no /proc, no shell).
        """
        code, out = self._exec(
            container,
            "c=0; for p in /proc/[0-9]*; do "
            "n=$(grep '(deleted)' $p/maps 2>/dev/null "
            "| grep -vE ' (/dev/|/memfd:|/SYSV|/anon|/drm|/i915)' "
            "| grep -cE ' /(usr|lib|bin|sbin|opt|etc)' ); "
            "case \"$n\" in ''|*[!0-9]*) n=0 ;; esac; "
            "[ \"$n\" -gt 0 ] && c=$((c+1)); done; echo $c",
        )
        if code != 0:
            return None
        try:
            return int((out or "0").strip().splitlines()[-1])
        except (ValueError, IndexError):
            return None

    def _image_info(self, container) -> dict:
        """Image identity and age. A stale image is the real risk in a container."""
        info = {
            "image_tag": None,
            "image_id": None,
            "image_created": None,
            "image_age_days": None,
        }
        try:
            image = container.image
            tags = image.tags or []
            info["image_tag"] = tags[0] if tags else (container.attrs.get("Config", {}).get("Image"))
            info["image_id"] = image.short_id

            created = image.attrs.get("Created")
            if created:
                # Docker returns nanosecond precision that fromisoformat rejects.
                cleaned = re.sub(r"\.(\d{6})\d+", r".\1", created).replace("Z", "+00:00")
                created_at = datetime.fromisoformat(cleaned)
                info["image_created"] = created_at.isoformat()
                info["image_age_days"] = (datetime.now(timezone.utc) - created_at).days
        except Exception as e:
            logger.debug("Could not read image info: %s", e)

        return info

    def _is_edge(self, container) -> bool:
        """Does this container publish a port to the host?

        A published port means the internet can reach it directly, which is what
        makes an unpatched package on it urgent rather than theoretical.
        """
        try:
            ports = container.attrs.get("NetworkSettings", {}).get("Ports") or {}
            return any(bindings for bindings in ports.values() if bindings)
        except Exception:
            return False

    # ── scanning ─────────────────────────────────────────────────────────

    def scan_one(self, container, include_packages: bool = False) -> dict:
        """Full posture for a single container. Blocking; run in a thread."""
        result = {
            "name": container.name,
            "id": container.short_id,
            "status": container.status,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "is_edge": self._is_edge(container),
        }
        result.update(self._image_info(container))

        if container.status != "running":
            result.update({
                "scannable": False,
                "reason": f"Container is {container.status}",
                "os": {}, "package_manager": None,
                "installed_count": 0, "pending": {"count": 0, "packages": []},
                "auto_update": {"enabled": False, "mechanism": None,
                                "detail": "Container not running"},
            })
            return result

        os_info = self._detect_os(container)
        manager = self._detect_package_manager(container)

        result["os"] = os_info
        result["package_manager"] = manager

        if not manager:
            # Distroless / scratch images have no package manager at all. That
            # is a good security property, not a scan failure.
            result.update({
                "scannable": False,
                "reason": "No package manager (distroless or scratch image)",
                "installed_count": 0,
                "pending": {"count": 0, "packages": []},
                "auto_update": {
                    "enabled": False, "mechanism": None,
                    "detail": "No package manager; rebuild the image to update",
                },
            })
            return result

        installed_count, packages = self._installed_packages(container, manager)
        pending = self._pending_updates(container, manager)
        auto_update = self._auto_update_status(container, manager)

        stale = self._stale_process_count(container)
        result.update({
            "scannable": True,
            "installed_count": installed_count,
            "pending": pending,
            "auto_update": auto_update,
            "stale_processes": stale,
            # Patched on disk but still running the old code — a restart is the
            # only thing that closes it.
            "restart_required": bool(stale),
        })

        if include_packages:
            result["installed_packages"] = packages

        result["risk"] = self._assess_risk(result)
        return result

    def _assess_risk(self, scan: dict) -> dict:
        """Turn the raw numbers into a level and a reason.

        Kept explicit rather than a score, so the UI can say *why* something is
        flagged instead of showing an unexplained number.
        """
        pending = scan.get("pending", {}) or {}
        count = pending.get("count", 0)
        security_count = pending.get("security_count")
        age = scan.get("image_age_days")
        edge = scan.get("is_edge")

        reasons = []
        level = "ok"

        if security_count:
            reasons.append(f"{security_count} security update(s) pending")
            level = "critical" if edge else "high"
        elif count:
            reasons.append(f"{count} package update(s) pending")
            level = "high" if edge else "medium"

        if age is not None:
            if age > 180:
                reasons.append(f"image is {age} days old")
                level = "critical" if edge else max_level(level, "high")
            elif age > 90:
                reasons.append(f"image is {age} days old")
                level = max_level(level, "medium")

        if scan.get("restart_required"):
            reasons.append(
                f"{scan.get('stale_processes')} process(es) still running pre-upgrade libraries "
                "— restart required"
            )
            # On an internet-facing container this is the live exposure, not a
            # tidiness issue: the patched file is on disk and the vulnerable
            # code is still executing.
            level = "critical" if edge else max_level(level, "high")

        if edge and level in ("medium", "high", "critical"):
            reasons.append("internet-facing")

        if not reasons:
            reasons.append("up to date")

        return {"level": level, "reasons": reasons}

    async def scan_all(
        self,
        name_filter: str = "ghostwire-proxy",
        include_packages: bool = False,
    ) -> list[dict]:
        """Scan every matching container concurrently."""
        if not self.client:
            return []

        loop = asyncio.get_event_loop()

        try:
            containers = await loop.run_in_executor(
                None,
                lambda: self.client.containers.list(
                    all=True,
                    filters={"name": name_filter} if name_filter else None,
                ),
            )
        except Exception as e:
            logger.warning("Could not list containers: %s", e)
            return []

        tasks = [
            asyncio.wait_for(
                loop.run_in_executor(None, self.scan_one, c, include_packages),
                timeout=EXEC_TIMEOUT_SECONDS * 3,
            )
            for c in containers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scans = []
        for container, result in zip(containers, results):
            if isinstance(result, Exception):
                logger.warning("Scan of %s failed: %s", container.name, result)
                scans.append({
                    "name": container.name,
                    "id": container.short_id,
                    "status": container.status,
                    "scannable": False,
                    "reason": f"Scan failed: {result}",
                    "risk": {"level": "unknown", "reasons": ["scan failed"]},
                })
            else:
                scans.append(result)

        # Worst first — the point of the page is to surface what needs attention.
        order = {"critical": 0, "high": 1, "medium": 2, "unknown": 3, "ok": 4}
        scans.sort(key=lambda s: order.get((s.get("risk") or {}).get("level", "unknown"), 3))
        return scans


_LEVELS = ("ok", "medium", "high", "critical")


def max_level(a: str, b: str) -> str:
    return a if _LEVELS.index(a) >= _LEVELS.index(b) else b


scanner = ContainerSecurityScanner()


# ── Applying updates ─────────────────────────────────────────────────────

# Upgrading takes far longer than inspecting: an apt or apk transaction has to
# download and unpack. Kept separate from EXEC_TIMEOUT_SECONDS so tightening the
# scan timeout never silently truncates an upgrade half-way through.
UPGRADE_TIMEOUT_SECONDS = 600

# Containers that must never be upgraded in place. Postgres is the one that
# matters: swapping its libraries under a running server risks the database
# itself, and it is a registry image that watchtower already keeps current by
# replacing the whole image — which is the correct mechanism for it.
DEFAULT_EXCLUDED = ("ghostwire-proxy-postgres",)


class UpgradeResult(dict):
    """Plain dict; named for readability at call sites."""


def _apply_command(manager: str, security_only: bool) -> Optional[str]:
    """The upgrade command for a package manager.

    Non-interactive throughout — an upgrade that stops to ask a question inside
    a container nobody is watching would hang until the timeout.
    """
    if manager == "apk":
        # apk has no notion of a security-only subset; everything or nothing.
        return "apk update && apk upgrade --no-cache"

    if manager == "apt-get":
        base = (
            "export DEBIAN_FRONTEND=noninteractive; apt-get update -qq && "
            "apt-get -y -qq -o Dpkg::Options::=--force-confold "
            "-o Dpkg::Options::=--force-confdef "
        )
        if security_only:
            # Restrict to the security suites so a routine patch run cannot
            # drag in unrelated version churn.
            return base + (
                "-t $(. /etc/os-release; echo ${VERSION_CODENAME}-security) upgrade"
            )
        return base + "upgrade"

    if manager in ("dnf", "yum"):
        return f"{manager} -y {'update --security' if security_only else 'update'}"

    return None


def apply_updates_sync(
    container,
    manager: Optional[str] = None,
    security_only: bool = True,
) -> dict:
    """Upgrade OS packages inside one running container. Blocking."""
    name = container.name
    result: dict = {
        "container": name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "applied": False,
        "manager": manager,
    }

    if container.status != "running":
        result["error"] = f"Container is {container.status}"
        return result

    if name in DEFAULT_EXCLUDED:
        result["error"] = "Excluded from in-place upgrades"
        return result

    manager = manager or scanner._detect_package_manager(container)
    result["manager"] = manager
    if not manager:
        result["error"] = "No package manager (distroless or scratch image)"
        return result

    command = _apply_command(manager, security_only)
    if not command:
        result["error"] = f"Unsupported package manager: {manager}"
        return result

    before = scanner._pending_updates(container, manager).get("count", 0)

    try:
        exec_result = container.exec_run(["/bin/sh", "-c", command], stdout=True, stderr=True)
        output = (exec_result.output or b"").decode("utf-8", errors="replace")
        code = exec_result.exit_code
    except Exception as e:
        result["error"] = f"Upgrade failed to run: {e}"
        return result

    after = scanner._pending_updates(container, manager).get("count", 0)

    result.update({
        "applied": code == 0,
        "exit_code": code,
        "pending_before": before,
        "pending_after": after,
        "upgraded": max(0, before - after),
        "stale_processes": scanner._stale_process_count(container),
        # The tail is what a human needs to see when it goes wrong; the whole
        # transcript of an apt run is noise in an alert.
        "output_tail": output.strip().splitlines()[-15:] if output.strip() else [],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })
    if code != 0:
        result["error"] = f"Package manager exited {code}"

    return result


async def apply_updates(
    container_name: str,
    security_only: bool = True,
    excluded: Optional[set[str]] = None,
    restart_if_needed: bool = True,
) -> dict:
    """Upgrade one container by name, and restart it if it is still running
    pre-upgrade libraries.

    The restart is the point. Upgrading rewrites the package on disk; every
    process that already mapped the old shared object keeps executing it until
    it is replaced. Without this step an internet-facing container reports
    "0 pending updates" while still running the vulnerable code.
    """
    if scanner.client is None:
        return {"container": container_name, "applied": False, "error": "Docker unavailable"}

    excluded = excluded or set()
    if container_name in excluded:
        return {"container": container_name, "applied": False, "error": "Excluded by policy"}

    try:
        container = scanner.client.containers.get(container_name)
    except Exception as e:
        return {"container": container_name, "applied": False, "error": f"Not found: {e}"}

    loop = asyncio.get_event_loop()
    result = await asyncio.wait_for(
        loop.run_in_executor(None, apply_updates_sync, container, None, security_only),
        timeout=UPGRADE_TIMEOUT_SECONDS,
    )

    result["restarted"] = False
    if restart_if_needed and result.get("applied") and result.get("stale_processes"):
        try:
            await loop.run_in_executor(None, lambda: container.restart(timeout=30))
            # Re-read: a healthy restart should clear every stale mapping.
            await asyncio.sleep(3)
            container.reload()
            remaining = await loop.run_in_executor(
                None, scanner._stale_process_count, container
            )
            result["restarted"] = True
            result["stale_processes_after_restart"] = remaining
            if remaining:
                result["warning"] = (
                    f"{remaining} process(es) still map replaced libraries after restart"
                )
            logger.info("Restarted %s to load upgraded libraries", container_name)
        except Exception as e:
            result["restart_error"] = str(e)
            logger.error("Could not restart %s after upgrade: %s", container_name, e)

    return result


async def apply_updates_all(
    name_filter: str = "ghostwire-proxy",
    security_only: bool = True,
    excluded: Optional[set[str]] = None,
    restart_if_needed: bool = True,
) -> list[dict]:
    """Upgrade every matching container, one at a time.

    Deliberately sequential. Upgrading the whole stack at once means every
    service is mid-transaction simultaneously, and if something breaks there is
    no healthy container left to serve while it is sorted out.
    """
    if scanner.client is None:
        return []

    excluded = set(excluded or ()) | set(DEFAULT_EXCLUDED)

    try:
        containers = scanner.client.containers.list(filters={"name": name_filter} if name_filter else None)
    except Exception as e:
        logger.warning("Could not list containers for upgrade: %s", e)
        return []

    results = []
    for container in containers:
        if container.name in excluded:
            results.append({
                "container": container.name, "applied": False, "skipped": True,
                "error": "Excluded by policy",
            })
            continue
        try:
            results.append(
                await apply_updates(container.name, security_only, excluded, restart_if_needed)
            )
        except asyncio.TimeoutError:
            results.append({
                "container": container.name, "applied": False,
                "error": f"Timed out after {UPGRADE_TIMEOUT_SECONDS}s",
            })
        except Exception as e:
            results.append({"container": container.name, "applied": False, "error": str(e)})

    return results
