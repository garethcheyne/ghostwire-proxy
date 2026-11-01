"""Retention deletes only rows older than the cutoff, across several batches."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.proxy_host import ProxyHost
from app.models.traffic_log import TrafficLog
from app.services import retention_service
from sqlalchemy import func, select

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.mark.asyncio
async def test_batch_delete_keeps_rows_newer_than_cutoff(db_session, monkeypatch):
    monkeypatch.setattr(retention_service, "BATCH_SIZE", 3)
    host = ProxyHost(domain_names=["a.example.test"], forward_scheme="http", forward_host="10.0.0.5", forward_port=80)
    db_session.add(host)
    await db_session.flush()
    old = [
        TrafficLog(id=str(uuid.uuid4()), proxy_host_id=host.id, timestamp=NOW - timedelta(days=40, minutes=i), client_ip="198.51.100.1",
                   request_method="GET", request_uri="/old", status=200)
        for i in range(7)
    ]
    new = [
        TrafficLog(id=str(uuid.uuid4()), proxy_host_id=host.id, timestamp=NOW - timedelta(days=10, minutes=i), client_ip="198.51.100.2",
                   request_method="GET", request_uri="/new", status=200)
        for i in range(5)
    ]
    db_session.add_all(old + new)
    await db_session.commit()

    deleted = await retention_service._batch_delete(db_session, "traffic_logs", "timestamp", NOW - timedelta(days=30))

    assert deleted == 7
    remaining = (await db_session.execute(select(TrafficLog.request_uri, func.count()).group_by(TrafficLog.request_uri))).all()
    assert dict(remaining) == {"/new": 5}
