"""System monitoring with Ghostwire Analytics, for every Ghostwire Python codebase.

The spec is ghostwire-suite/docs/analytics-reporting.md. This one file is copied verbatim into each
Python codebase (keep the copies identical; change it in ghostwire-suite/telemetry/python first).

Traces and metrics go over OTLP/HTTP to the Analytics site in the app's Settings. The settings are
read at run time through the app's own cached getter, so monitoring can be switched on, off or
re-pointed without a restart. While it is off nothing is sampled or sent.

Reporting only observes: nothing here raises into the app (setup included), exports run on
background threads with short timeouts, and a slow or dead Analytics never slows a request.

    import ghostwire_telemetry

    ghostwire_telemetry.setup(get_analytics_config, service_name="api",
                              service_namespace="ghostwire-secure", app=app, sqlalchemy_engine=engine)
    app.include_router(ghostwire_telemetry.make_otlp_relay_router(get_analytics_config))

    with ghostwire_telemetry.job("collect-github"):   # or @ghostwire_telemetry.job("collect-github")
        ...
    ghostwire_telemetry.heartbeat()                    # once per worker loop
"""

import contextlib
import functools
import inspect
import ipaddress
import logging
import os
import socket
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import (
    Counter,
    Histogram,
    MeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    MetricExporter,
    MetricExportResult,
    MetricsData,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import Decision, ParentBased, Sampler, SamplingResult, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode

try:  # opentelemetry-instrumentation; present whenever the instrumentation packages are
    from opentelemetry.instrumentation.utils import suppress_instrumentation
except ImportError:  # pragma: no cover
    suppress_instrumentation = contextlib.nullcontext  # type: ignore[assignment]

__all__ = ["IGNORED_PATHS", "force_flush", "heartbeat", "job", "make_otlp_relay_router", "setup", "shutdown"]

log = logging.getLogger("ghostwire.telemetry")

#: Health checks and the relay: frequent, uninteresting, and the relay would echo. Regexes, searched in the URL.
IGNORED_PATHS = ["/health$", "/api/heartbeat", "/internal/otlp/"]

EXPORT_TIMEOUT_S = 10
CONFIG_REFRESH_S = 5  # how stale the sampler's view may get; the app's own getter caches for about a minute
WARN_EVERY_S = 600
RELAY_MAX_BODY = 10 * 1024 * 1024
RELAY_SIGNALS = {"metrics", "traces"}
RELAY_CONTENT_TYPES = {"application/x-protobuf", "application/json"}

GetConfig = Callable[[], Any]


# --- Settings -------------------------------------------------------------------------------------


def _field(config: Any, name: str) -> Any:
    """Reads a field from a dict, a dataclass or any object, so each app can keep its own type."""
    if config is None:
        return None
    if isinstance(config, dict):
        return config.get(name)
    return getattr(config, name, None)


def _target(config: Any) -> tuple[str, str] | None:
    """(url, key) while monitoring is on, else None. Monitoring needs the ingest key."""
    url = str(_field(config, "url") or "").strip().rstrip("/")
    key = str(_field(config, "ingest_key") or "").strip()
    return (url, key) if url and key else None


def _sample_ratio(config: Any) -> float:
    try:
        sample = float(_field(config, "trace_sample"))
    except (TypeError, ValueError):
        return 1.0
    return min(100.0, max(0.0, sample)) / 100.0


class _LiveConfig:
    """The latest settings. Exports read fresh; the sampler reads the last value and refreshes in the background."""

    def __init__(self, get_config: GetConfig):
        self._get_config = get_config
        self._value: Any = None
        self._read_at = 0.0
        self._lock = threading.Lock()
        self._refreshing = False
        self._warned_async = False

    def refresh(self) -> Any:
        value = None
        try:
            with suppress_instrumentation():  # the getter may query the database; don't trace that
                value = self._get_config()
            if inspect.isawaitable(value):
                if hasattr(value, "close"):
                    value.close()
                if not self._warned_async:
                    self._warned_async = True
                    log.warning(
                        "ghostwire_telemetry: get_config must be a plain function, not async; monitoring stays off"
                    )
                value = None
        except Exception:  # a broken getter means "off", never an error in the app
            value = None
        self._value = value
        self._read_at = time.monotonic()
        return value

    def peek(self) -> Any:
        if time.monotonic() - self._read_at > CONFIG_REFRESH_S:
            with self._lock:
                start = not self._refreshing
                self._refreshing = True
            if start:
                threading.Thread(target=self._background_refresh, name="ghostwire-config", daemon=True).start()
        return self._value

    def _background_refresh(self) -> None:
        try:
            self.refresh()
        finally:
            self._refreshing = False


class _Warner:
    """Export failures say so in the log now and then, never per batch and never as an exception."""

    def __init__(self, what: str):
        self._what = what
        self._last = -WARN_EVERY_S

    def __call__(self, reason: object = "no answer") -> None:
        now = time.monotonic()
        if now - self._last < WARN_EVERY_S:
            return
        self._last = now
        log.warning("Couldn't send %s to Ghostwire Analytics (%s). Retrying quietly.", self._what, reason)


# --- Switchable exporters -------------------------------------------------------------------------


class _ExporterSlot:
    """One inner OTLP exporter per URL and key, rebuilt when Settings change; the old one is shut down."""

    def __init__(self, build: Callable[[str, str], Any]):
        self._build = build
        self._id: tuple[str, str] | None = None
        self._exporter: Any = None
        self._lock = threading.Lock()

    def get(self, target: tuple[str, str]) -> Any:
        with self._lock:
            if self._id != target:
                old = self._exporter
                self._exporter = self._build(*target)
                self._id = target
                if old is not None:
                    with contextlib.suppress(Exception):
                        old.shutdown()
            return self._exporter

    def close(self) -> None:
        with self._lock:
            old, self._exporter, self._id = self._exporter, None, None
        if old is not None:
            with contextlib.suppress(Exception):
                old.shutdown()


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _off_is_quiet(response: Any, *args: Any, **kwargs: Any) -> Any:
    """A 404 is the app's relay saying monitoring is off: the batch is dropped, which is what off means,
    so the exporter sees it as sent and logs nothing."""
    if response.status_code == 404:
        response.status_code = 200
    return response


def _session() -> Any:
    import requests  # a dependency of the OTLP exporter

    session = requests.Session()
    session.hooks["response"].append(_off_is_quiet)
    return session


class SwitchableSpanExporter(SpanExporter):
    """Sends spans to <url>/v1/traces with the key from Settings, or drops them while monitoring is off."""

    def __init__(self, live: _LiveConfig):
        self._live = live
        self._slot = _ExporterSlot(
            lambda url, key: OTLPSpanExporter(
                endpoint=f"{url}/v1/traces", headers=_headers(key), timeout=EXPORT_TIMEOUT_S, session=_session()
            )
        )
        self._warn = _Warner("traces")

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            target = _target(self._live.refresh())
            if target is None:
                return SpanExportResult.SUCCESS  # off: dropped on purpose
            result = self._slot.get(target).export(spans)
        except Exception as error:
            self._warn(error)
            return SpanExportResult.FAILURE
        if result is not SpanExportResult.SUCCESS:
            self._warn()
        return result

    def shutdown(self) -> None:
        self._slot.close()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


# Delta for counters and histograms: each export says what happened in that interval, which is what
# Analytics rolls up per minute, and a restart never looks like a counter going backwards.
_DELTA = {
    Counter: AggregationTemporality.DELTA,
    Histogram: AggregationTemporality.DELTA,
    ObservableCounter: AggregationTemporality.DELTA,
    ObservableGauge: AggregationTemporality.DELTA,
    UpDownCounter: AggregationTemporality.CUMULATIVE,
    ObservableUpDownCounter: AggregationTemporality.CUMULATIVE,
}


class SwitchableMetricExporter(MetricExporter):
    """Sends metrics to <url>/v1/metrics with the key from Settings, or drops them while monitoring is off."""

    def __init__(self, live: _LiveConfig):
        super().__init__(preferred_temporality=_DELTA)
        self._live = live
        self._slot = _ExporterSlot(
            lambda url, key: OTLPMetricExporter(
                endpoint=f"{url}/v1/metrics",
                headers=_headers(key),
                timeout=EXPORT_TIMEOUT_S,
                preferred_temporality=_DELTA,
                session=_session(),
            )
        )
        self._warn = _Warner("metrics")

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any) -> MetricExportResult:
        try:
            target = _target(self._live.refresh())
            if target is None:
                return MetricExportResult.SUCCESS
            result = self._slot.get(target).export(metrics_data, timeout_millis=timeout_millis)
        except Exception as error:
            self._warn(error)
            return MetricExportResult.FAILURE
        if result is not MetricExportResult.SUCCESS:
            self._warn()
        return result

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        self._slot.close()


class GhostwireSampler(Sampler):
    """The trace sampling % from Settings as it is now: follows the parent's decision when there is one,
    otherwise keeps that share of traces by trace ID. Records nothing while monitoring is off. Metrics
    aren't sampled; they count every request."""

    def __init__(self, live: _LiveConfig):
        self._live = live
        self._by_ratio: dict[float, Sampler] = {}

    def should_sample(self, parent_context, trace_id, name, kind=None, attributes=None, links=None, trace_state=None):
        config = self._live.peek()
        if _target(config) is None:
            return SamplingResult(Decision.DROP)
        ratio = _sample_ratio(config)
        sampler = self._by_ratio.get(ratio)
        if sampler is None:
            sampler = self._by_ratio[ratio] = ParentBased(TraceIdRatioBased(ratio))
        return sampler.should_sample(parent_context, trace_id, name, kind, attributes, links, trace_state)

    def get_description(self) -> str:
        return "GhostwireSampler"


# --- Setup ----------------------------------------------------------------------------------------

_state: dict[str, Any] = {}
_state_lock = threading.Lock()


def _instrument(label: str, module: str, cls: str, **kwargs: Any) -> None:
    """Instruments one library if both it and its instrumentation are installed; quiet otherwise."""
    try:
        instrumentor_module = __import__(module, fromlist=[cls])
    except ImportError:
        return
    try:
        from opentelemetry.instrumentation.dependencies import get_dependency_conflicts

        instrumentor = getattr(instrumentor_module, cls)()
        if instrumentor.is_instrumented_by_opentelemetry:
            return
        if not kwargs.get("skip_dep_check") and get_dependency_conflicts(instrumentor.instrumentation_dependencies()):
            return  # the library isn't installed (or is a version it doesn't support): nothing to instrument
        instrumentor.instrument(**kwargs)
        _state.setdefault("instrumented", []).append(label)
    except Exception as error:
        log.warning("ghostwire_telemetry: couldn't instrument %s (%s)", label, error)


def _engines(engine: Any) -> list[Any]:
    """SQLAlchemy engines, sync or async (an AsyncEngine is instrumented through its sync_engine)."""
    if engine is None:
        return []
    items = list(engine) if isinstance(engine, (list, tuple)) else [engine]
    return [getattr(e, "sync_engine", e) for e in items]


def setup(
    get_config: GetConfig,
    *,
    service_name: str,
    service_namespace: str,
    service_version: str | None = None,
    app: Any = None,
    sqlalchemy_engine: Any = None,
    environment: str | None = None,
    metric_interval_s: float = 30,
    instrument_asyncpg: bool | None = None,
    ignored_paths: Iterable[str] | None = None,
) -> bool:
    """Starts tracing and metrics for this process. Returns True when set up (or already set up).

    get_config() returns the current settings (a dict, dataclass or object with url, website_id,
    ingest_key and trace_sample 0-100) while monitoring is on, otherwise None. It must be a plain
    (not async) function, fast and cached by the app: it is called from export threads every few
    seconds. This module caches nothing itself.

    app: a FastAPI app to instrument. sqlalchemy_engine: an Engine or AsyncEngine (or a list).
    instrument_asyncpg: defaults to True only without a SQLAlchemy engine, so SQLAlchemy over asyncpg
    doesn't record every query twice. Never raises.
    """
    with _state_lock:
        if _state.get("ready"):
            if app is not None:
                _instrument_fastapi(app, ignored_paths)
            return True
        try:
            return _setup(
                get_config,
                service_name=service_name,
                service_namespace=service_namespace,
                service_version=service_version,
                app=app,
                sqlalchemy_engine=sqlalchemy_engine,
                environment=environment,
                metric_interval_s=metric_interval_s,
                instrument_asyncpg=instrument_asyncpg,
                ignored_paths=ignored_paths,
            )
        except Exception as error:
            log.warning("ghostwire_telemetry: monitoring didn't start (%s); the app runs without it", error)
            return False


def _setup(
    get_config,
    *,
    service_name,
    service_namespace,
    service_version,
    app,
    sqlalchemy_engine,
    environment,
    metric_interval_s,
    instrument_asyncpg,
    ignored_paths,
) -> bool:
    # Stable HTTP and database semantic conventions (http.server.request.duration in seconds), the
    # same names the Node.js apps send. Must be set before the first instrumentor runs.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http,database")

    live = _LiveConfig(get_config)
    environment = (
        environment or os.environ.get("DEPLOYMENT_ENVIRONMENT") or os.environ.get("ENVIRONMENT") or "production"
    )
    version = service_version or os.environ.get("APP_VERSION")
    attributes = {
        "service.name": service_name,
        "service.namespace": service_namespace,
        "deployment.environment": environment,  # the spec's name
        "deployment.environment.name": environment,  # the current semantic-conventions name
        "host.name": socket.gethostname(),
        "process.pid": os.getpid(),
    }
    if version:
        attributes["service.version"] = version
    resource = Resource.create(attributes)

    tracer_provider = TracerProvider(resource=resource, sampler=GhostwireSampler(live))
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            SwitchableSpanExporter(live),
            schedule_delay_millis=5000,
            export_timeout_millis=(EXPORT_TIMEOUT_S + 5) * 1000,
            max_queue_size=2048,
        )
    )
    interval_ms = max(1000, int(metric_interval_s * 1000))
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                SwitchableMetricExporter(live),
                export_interval_millis=interval_ms,
                export_timeout_millis=min((EXPORT_TIMEOUT_S + 5) * 1000, interval_ms),
            )
        ],
    )
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)
    _state.update(ready=True, tracer_provider=tracer_provider, meter_provider=meter_provider, live=live)
    threading.Thread(target=live.refresh, name="ghostwire-config", daemon=True).start()

    providers = {"tracer_provider": tracer_provider, "meter_provider": meter_provider}
    engines = _engines(sqlalchemy_engine)
    if engines:
        # The instrumentation declares sqlalchemy<2.1, but works with 2.1 (it uses engine events).
        _instrument(
            "sqlalchemy",
            "opentelemetry.instrumentation.sqlalchemy",
            "SQLAlchemyInstrumentor",
            engines=engines,
            skip_dep_check=True,
            enable_commenter=False,
            **providers,
        )
    if instrument_asyncpg if instrument_asyncpg is not None else not engines:
        _instrument("asyncpg", "opentelemetry.instrumentation.asyncpg", "AsyncPGInstrumentor", **providers)
    _instrument("redis", "opentelemetry.instrumentation.redis", "RedisInstrumentor", **providers)
    _instrument("httpx", "opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor", **providers)
    _instrument("requests", "opentelemetry.instrumentation.requests", "RequestsInstrumentor", **providers)
    _instrument(
        "aiohttp-client", "opentelemetry.instrumentation.aiohttp_client", "AioHttpClientInstrumentor", **providers
    )
    # elasticsearch-py 8.13+ traces itself through the global tracer provider; the contrib
    # instrumentation (stopped at 0.64b0) only matters for older clients, if it is installed.
    _instrument(
        "elasticsearch", "opentelemetry.instrumentation.elasticsearch", "ElasticsearchInstrumentor", **providers
    )
    if app is not None:
        _instrument_fastapi(app, ignored_paths)
    log.info("ghostwire_telemetry: ready (%s)", ", ".join(_state.get("instrumented", [])) or "no libraries")
    return True


def _instrument_fastapi(app: Any, ignored_paths: Iterable[str] | None) -> None:
    if getattr(app, "_is_instrumented_by_opentelemetry", False):
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        log.warning(
            "ghostwire_telemetry: opentelemetry-instrumentation-fastapi isn't installed; requests aren't traced"
        )
        return
    try:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=_state["tracer_provider"],
            meter_provider=_state["meter_provider"],
            excluded_urls=",".join(ignored_paths if ignored_paths is not None else IGNORED_PATHS),
        )
        _state.setdefault("instrumented", []).append("fastapi")
    except Exception as error:
        log.warning("ghostwire_telemetry: couldn't instrument the FastAPI app (%s)", error)


def force_flush(timeout_s: float = 15) -> None:
    """Sends what's queued now (e.g. before a one-shot job exits). Never raises."""
    for name in ("tracer_provider", "meter_provider"):
        provider = _state.get(name)
        if provider is not None:
            with contextlib.suppress(Exception):
                provider.force_flush(int(timeout_s * 1000))


def shutdown() -> None:
    """Flushes and stops (at process exit the SDK does this by itself). Never raises."""
    for name in ("tracer_provider", "meter_provider"):
        provider = _state.get(name)
        if provider is not None:
            with contextlib.suppress(Exception):
                provider.shutdown()


# --- Worker helpers -------------------------------------------------------------------------------

_JOB_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]
_instruments: dict[str, Any] = {}


def _instrument_for(name: str) -> Any:
    """Created on first use from the global meter, so it works before setup() (and binds after it)."""
    found = _instruments.get(name)
    if found is None:
        meter = metrics.get_meter("ghostwire")
        if name == "duration":
            found = meter.create_histogram(
                "ghostwire.job.duration",
                unit="s",
                description="How long each job run took",
                explicit_bucket_boundaries_advisory=_JOB_BUCKETS,
            )
        elif name == "runs":
            found = meter.create_counter("ghostwire.job.runs", unit="{run}", description="Job runs, by outcome")
        else:
            found = meter.create_counter("ghostwire.heartbeat", unit="{beat}", description="Worker loop heartbeats")
        _instruments[name] = found
    return found


class job:  # reads as a function: `with job("x"):` / `@job("x")`
    """One run of a background job: a span named after it, plus `ghostwire.job.duration` (seconds) and
    `ghostwire.job.runs`, both with attributes `job` and `outcome` (ok or error). An exception is
    recorded on the span and re-raised unchanged. Works as a context manager (sync or async) and as a
    decorator on sync or async functions."""

    def __init__(self, name: str, **attributes: Any):
        self.name = name
        self.attributes = attributes
        self._span_cm: Any = None
        self._started = 0.0

    def __enter__(self) -> trace.Span:
        self._started = time.perf_counter()
        try:
            self._span_cm = trace.get_tracer("ghostwire").start_as_current_span(
                f"job {self.name}",
                kind=SpanKind.INTERNAL,
                attributes={"job": self.name, **self.attributes},
                record_exception=True,
                set_status_on_exception=True,
            )
            return self._span_cm.__enter__()
        except Exception:
            self._span_cm = None
            return trace.INVALID_SPAN

    def __exit__(self, exc_type, exc, tb) -> bool:
        outcome = "ok" if exc_type is None else "error"
        with contextlib.suppress(Exception):
            labels = {"job": self.name, "outcome": outcome}
            _instrument_for("duration").record(time.perf_counter() - self._started, labels)
            _instrument_for("runs").add(1, labels)
            if exc_type is None and self._span_cm is not None:
                trace.get_current_span().set_status(Status(StatusCode.OK))
        if self._span_cm is not None:
            with contextlib.suppress(Exception):
                self._span_cm.__exit__(exc_type, exc, tb)
        return False  # never swallow the job's exception

    async def __aenter__(self) -> trace.Span:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return self.__exit__(exc_type, exc, tb)

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        name, attributes = self.name, self.attributes
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def run_async(*args: Any, **kwargs: Any) -> Any:
                async with job(name, **attributes):
                    return await fn(*args, **kwargs)

            return run_async

        @functools.wraps(fn)
        def run(*args: Any, **kwargs: Any) -> Any:
            with job(name, **attributes):
                return fn(*args, **kwargs)

        return run


def heartbeat(**attributes: Any) -> None:
    """Counts one loop of a worker (`ghostwire.heartbeat`). Call it every loop, busy or idle: Analytics
    shows a service whose heartbeat stops as down. Never raises."""
    with contextlib.suppress(Exception):
        _instrument_for("heartbeat").add(1, attributes or None)


# --- OTLP relay for the stack's Collector ---------------------------------------------------------

_PRIVATE_NETWORKS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128", "fc00::/7", "fe80::/10")
]


def is_private_address(raw: str) -> bool:
    """Loopback, RFC 1918, IPv6 loopback, unique-local and link-local; IPv4-mapped IPv6 is unwrapped."""
    value = raw.strip().strip('"')
    if value.startswith("["):
        value = value[1 : value.find("]")]
    elif value.count(":") == 1:  # v4:port
        value = value.split(":")[0]
    value = value.split("%")[0]
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return any(address in network for network in _PRIVATE_NETWORKS if network.version == address.version)


def _from_inside_stack(peer: str | None, headers: Any) -> bool:
    """The socket peer and every address the request was forwarded for must be private: anything that
    came through the reverse proxy from outside carries a public address in X-Forwarded-For."""
    addresses = [peer or ""]
    addresses += [a for a in (headers.get("x-forwarded-for") or "").split(",") if a.strip()]
    if headers.get("x-real-ip"):
        addresses.append(headers["x-real-ip"])
    for part in (headers.get("forwarded") or "").replace(",", ";").split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() == "for" and value:
            addresses.append(value)
    return all(is_private_address(a) for a in addresses)


def make_otlp_relay_router(get_config: GetConfig, *, timeout_s: float = 10, max_body: int = RELAY_MAX_BODY):
    """A FastAPI router with POST /internal/otlp/v1/{metrics,traces}: the stack's OpenTelemetry Collector
    (ghostwire-<app>-otel) sends container and host metrics here, and this forwards them to Analytics
    with the URL and ingest key from Settings, so the Collector's config never holds either.

    Only from private addresses (the stack's Docker network); 404 while monitoring is off, so the
    Collector drops what it holds instead of queueing it. Mount it without a prefix:

        app.include_router(ghostwire_telemetry.make_otlp_relay_router(get_analytics_config))
    """
    import httpx
    from fastapi import APIRouter, Request, Response
    from starlette.concurrency import run_in_threadpool

    router = APIRouter()
    client_holder: dict[str, httpx.AsyncClient] = {}

    def client() -> httpx.AsyncClient:
        found = client_holder.get("client")
        if found is None or found.is_closed:
            found = client_holder["client"] = httpx.AsyncClient(timeout=timeout_s)
        return found

    def empty(status: int) -> Response:
        return Response(status_code=status, headers={"Cache-Control": "no-store"})

    def read_config() -> Any:
        try:
            return get_config()
        except Exception:
            return None

    @router.post("/internal/otlp/v1/{signal}", include_in_schema=False)
    async def otlp_relay(signal: str, request: Request) -> Response:
        if signal not in RELAY_SIGNALS:
            return empty(404)
        if not _from_inside_stack(request.client.host if request.client else None, request.headers):
            return empty(403)

        config = await run_in_threadpool(read_config)
        if inspect.isawaitable(config):
            config = await config
        target = _target(config)
        if target is None:
            return empty(404)
        url, key = target

        content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in RELAY_CONTENT_TYPES:
            return empty(415)
        try:
            if int(request.headers.get("content-length") or 0) > max_body:
                return empty(413)
        except ValueError:
            return empty(400)
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > max_body:
                return empty(413)

        headers = {"content-type": content_type, "authorization": f"Bearer {key}"}
        if request.headers.get("content-encoding"):
            headers["content-encoding"] = request.headers["content-encoding"]
        try:
            with suppress_instrumentation():  # forwarding monitoring data shouldn't produce more of it
                upstream = await client().post(f"{url}/v1/{signal}", content=bytes(body), headers=headers)
        except httpx.TimeoutException:
            return empty(504)
        except httpx.HTTPError:
            return empty(502)
        response_headers = {"Cache-Control": "no-store"}
        if upstream.headers.get("content-type"):
            response_headers["content-type"] = upstream.headers["content-type"]
        return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)

    return router
