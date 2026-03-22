"""Tests for model creation and basic validation."""

import pytest
import uuid
from datetime import datetime, timezone

from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.setting import Setting
from app.models.rate_limit import RateLimitRule, GeoipRule
from app.models.waf import WafRuleSet, WafRule, ThreatEvent, ThreatActor, ThreatThreshold
from app.models.certificate import Certificate
from app.models.proxy_host import ProxyHost
from app.models.access_list import AccessList, AccessListEntry
from app.models.backup import Backup
from app.models.traffic_log import TrafficLog
from app.models.alert import AlertChannel, AlertPreference
from app.models.analytics import AnalyticsHourly, AnalyticsDaily


class TestUserModel:
    """Tests for User model."""

    @pytest.mark.asyncio
    async def test_create_user(self, db_session):
        user = User(
            id=str(uuid.uuid4()),
            email="model@test.com",
            name="Model Test",
            password_hash="$2b$04$fakehash",
            role="user",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.email == "model@test.com"
        assert user.is_active is True
        assert user.signin_count == 0

    @pytest.mark.asyncio
    async def test_user_defaults(self, db_session):
        user = User(
            id=str(uuid.uuid4()),
            email="defaults@test.com",
            name="Defaults",
            password_hash="hash",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.role == "user"
        assert user.is_active is True


class TestAuditLogModel:
    """Tests for AuditLog model."""

    @pytest.mark.asyncio
    async def test_create_audit_log(self, db_session):
        log = AuditLog(
            action="test_action",
            user_id="user-1",
            ip_address="127.0.0.1",
            details="Test details",
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.action == "test_action"
        assert log.id is not None
        assert log.timestamp is not None


class TestSettingModel:
    """Tests for Setting model."""

    @pytest.mark.asyncio
    async def test_create_setting(self, db_session):
        setting = Setting(key="test_setting", value="test_value")
        db_session.add(setting)
        await db_session.commit()
        await db_session.refresh(setting)

        assert setting.key == "test_setting"
        assert setting.value == "test_value"


class TestRateLimitRuleModel:
    """Tests for RateLimitRule model."""

    @pytest.mark.asyncio
    async def test_create_rate_limit_rule(self, db_session):
        rule = RateLimitRule(
            id=str(uuid.uuid4()),
            name="Test Rule",
            requests_per_minute=60,
            burst_size=10,
            action="reject",
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        assert rule.name == "Test Rule"
        assert rule.requests_per_minute == 60


class TestWafModels:
    """Tests for WAF-related models."""

    @pytest.mark.asyncio
    async def test_create_waf_rule_set(self, db_session):
        rule_set = WafRuleSet(
            id=str(uuid.uuid4()),
            name="Test Set",
            description="Test rule set",
            enabled=True,
        )
        db_session.add(rule_set)
        await db_session.commit()
        await db_session.refresh(rule_set)

        assert rule_set.name == "Test Set"

    @pytest.mark.asyncio
    async def test_create_waf_rule(self, db_session):
        rule_set = WafRuleSet(
            id="rs-1",
            name="Test Set",
            enabled=True,
        )
        db_session.add(rule_set)
        await db_session.commit()

        rule = WafRule(
            id=str(uuid.uuid4()),
            rule_set_id="rs-1",
            name="XSS Rule",
            pattern="<script>",
            category="xss",
            severity="high",
            action="block",
            enabled=True,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        assert rule.name == "XSS Rule"
        assert rule.category == "xss"

    @pytest.mark.asyncio
    async def test_create_threat_actor(self, db_session):
        actor = ThreatActor(
            id=str(uuid.uuid4()),
            ip_address="192.0.2.1",
            current_status="monitored",
            threat_score=50,
            total_events=5,
        )
        db_session.add(actor)
        await db_session.commit()
        await db_session.refresh(actor)

        assert actor.ip_address == "192.0.2.1"
        assert actor.threat_score == 50

    @pytest.mark.asyncio
    async def test_create_threat_threshold(self, db_session):
        threshold = ThreatThreshold(
            id=str(uuid.uuid4()),
            name="High Threat",
            threat_score=80,
            response_action="block",
            enabled=True,
        )
        db_session.add(threshold)
        await db_session.commit()
        await db_session.refresh(threshold)

        assert threshold.name == "High Threat"


class TestCertificateModel:
    """Tests for Certificate model."""

    @pytest.mark.asyncio
    async def test_create_certificate(self, db_session):
        cert = Certificate(
            id=str(uuid.uuid4()),
            name="Test Cert",
            domain_names=["test.example.com"],
            is_letsencrypt=False,
            status="valid",
        )
        db_session.add(cert)
        await db_session.commit()
        await db_session.refresh(cert)

        assert cert.name == "Test Cert"
        assert cert.status == "valid"


class TestProxyHostModel:
    """Tests for ProxyHost model."""

    @pytest.mark.asyncio
    async def test_create_proxy_host(self, db_session):
        host = ProxyHost(
            id=str(uuid.uuid4()),
            domain_names=["proxy.example.com"],
            forward_scheme="http",
            forward_host="backend",
            forward_port=8080,
            enabled=True,
        )
        db_session.add(host)
        await db_session.commit()
        await db_session.refresh(host)

        assert host.domain_names == ["proxy.example.com"]
        assert host.forward_port == 8080


class TestAccessListModel:
    """Tests for AccessList model."""

    @pytest.mark.asyncio
    async def test_create_access_list(self, db_session):
        acl = AccessList(
            id=str(uuid.uuid4()),
            name="Test ACL",
            mode="whitelist",
        )
        db_session.add(acl)
        await db_session.commit()
        await db_session.refresh(acl)

        assert acl.name == "Test ACL"
        assert acl.mode == "whitelist"


class TestTrafficLogModel:
    """Tests for TrafficLog model."""

    @pytest.mark.asyncio
    async def test_create_traffic_log(self, db_session):
        # TrafficLog requires proxy_host_id (FK), create a proxy host first
        from app.models.proxy_host import ProxyHost
        host = ProxyHost(
            id="ph-traffic-test",
            domain_names=["traffic.test"],
            forward_scheme="http",
            forward_host="backend",
            forward_port=80,
        )
        db_session.add(host)
        await db_session.commit()

        log = TrafficLog(
            id=str(uuid.uuid4()),
            proxy_host_id="ph-traffic-test",
            client_ip="10.0.0.1",
            request_method="GET",
            request_uri="/test",
            status=200,
            response_time=50,
            bytes_sent=1024,
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.client_ip == "10.0.0.1"
        assert log.status == 200


class TestAlertModels:
    """Tests for Alert-related models."""

    @pytest.mark.asyncio
    async def test_create_alert_channel(self, db_session):
        channel = AlertChannel(
            id=str(uuid.uuid4()),
            user_id="user-1",
            name="Slack Channel",
            channel_type="slack",
            enabled=True,
        )
        db_session.add(channel)
        await db_session.commit()
        await db_session.refresh(channel)

        assert channel.channel_type == "slack"

    @pytest.mark.asyncio
    async def test_create_alert_preference(self, db_session):
        pref = AlertPreference(
            id=str(uuid.uuid4()),
            user_id="user-1",
            alert_type="security",
            min_severity="high",
            enabled=True,
        )
        db_session.add(pref)
        await db_session.commit()
        await db_session.refresh(pref)

        assert pref.alert_type == "security"
        assert pref.min_severity == "high"
