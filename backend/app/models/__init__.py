# Import all models to ensure they're registered with SQLAlchemy
from app.models.access_list import AccessList, AccessListEntry
from app.models.alert import AlertChannel, AlertPreference, PushSubscription
from app.models.analytics import AnalyticsDaily, AnalyticsGeo, AnalyticsHourly
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.auth import AuthAccount, AuthSession, AuthVerification
from app.models.auth_wall import AuthProvider, AuthWall, LdapConfig, LocalAuthUser
from app.models.auth_wall_session import AuthWallSession
from app.models.backup import Backup, BackupSettings
from app.models.certificate import Certificate
from app.models.dns_provider import DnsProvider, DnsZone
from app.models.firewall import FirewallBlocklist, FirewallConnector
from app.models.honeypot import AbuseIPDBBlacklistEntry, HoneypotHit, HoneypotTrap, IpEnrichment
from app.models.known_ip import KnownIp
from app.models.proxy_host import ProxyHost, ProxyLocation, UpstreamServer, UpstreamServerEvent
from app.models.rate_limit import GeoipRule, GeoipSettings, RateLimitRule
from app.models.setting import Setting
from app.models.system_metrics import ContainerMetrics, SystemMetrics
from app.models.traffic_log import TrafficLog
from app.models.traffic_rollup import TrafficRollupHourly, TrafficRollupMethodHourly, TrafficRollupState
from app.models.update import BaseImageVersion, UpdateHistory, UpdateSettings
from app.models.user import User
from app.models.waf import ThreatActor, ThreatEvent, ThreatThreshold, WafRule, WafRuleSet

__all__ = [
    "AbuseIPDBBlacklistEntry",
    "AccessList",
    "AccessListEntry",
    "AlertChannel",
    "AlertPreference",
    "AnalyticsDaily",
    "AnalyticsGeo",
    "AnalyticsHourly",
    "ApiKey",
    "AuditLog",
    "AuthAccount",
    "AuthProvider",
    "AuthSession",
    "AuthVerification",
    "AuthWall",
    "AuthWallSession",
    "Backup",
    "BackupSettings",
    "BaseImageVersion",
    "Certificate",
    "ContainerMetrics",
    "DnsProvider",
    "DnsZone",
    "FirewallBlocklist",
    "FirewallConnector",
    "GeoipRule",
    "GeoipSettings",
    "HoneypotHit",
    "HoneypotTrap",
    "IpEnrichment",
    "KnownIp",
    "LdapConfig",
    "LocalAuthUser",
    "ProxyHost",
    "ProxyLocation",
    "PushSubscription",
    "RateLimitRule",
    "Setting",
    "SystemMetrics",
    "ThreatActor",
    "ThreatEvent",
    "ThreatThreshold",
    "TrafficLog",
    "TrafficRollupHourly",
    "TrafficRollupMethodHourly",
    "TrafficRollupState",
    "UpdateHistory",
    "UpdateSettings",
    "UpstreamServer",
    "UpstreamServerEvent",
    "User",
    "WafRule",
    "WafRuleSet",
]
