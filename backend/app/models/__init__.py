# Import all models to ensure they're registered with SQLAlchemy
from app.models.user import User
from app.models.proxy_host import ProxyHost, UpstreamServer, ProxyLocation
from app.models.certificate import Certificate
from app.models.access_list import AccessList, AccessListEntry
from app.models.auth_wall import AuthWall, LocalAuthUser, AuthProvider, LdapConfig
from app.models.auth_wall_session import AuthWallSession
from app.models.traffic_log import TrafficLog
from app.models.audit_log import AuditLog
from app.models.setting import Setting
from app.models.dns_provider import DnsProvider, DnsZone
from app.models.waf import WafRuleSet, WafRule, ThreatEvent, ThreatActor, ThreatThreshold
from app.models.firewall import FirewallConnector, FirewallBlocklist
from app.models.alert import PushSubscription, AlertChannel, AlertPreference
from app.models.rate_limit import RateLimitRule, GeoipSettings, GeoipRule
from app.models.analytics import AnalyticsHourly, AnalyticsDaily, AnalyticsGeo
from app.models.system_metrics import SystemMetrics, ContainerMetrics
from app.models.backup import Backup, BackupSettings
from app.models.update import UpdateHistory, BaseImageVersion, UpdateSettings
from app.models.honeypot import HoneypotTrap, HoneypotHit, IpEnrichment

__all__ = [
    "User",
    "ProxyHost",
    "UpstreamServer",
    "ProxyLocation",
    "Certificate",
    "AccessList",
    "AccessListEntry",
    "AuthWall",
    "LocalAuthUser",
    "AuthProvider",
    "LdapConfig",
    "AuthWallSession",
    "TrafficLog",
    "AuditLog",
    "Setting",
    "DnsProvider",
    "DnsZone",
    "WafRuleSet",
    "WafRule",
    "ThreatEvent",
    "ThreatActor",
    "ThreatThreshold",
    "FirewallConnector",
    "FirewallBlocklist",
    "PushSubscription",
    "AlertChannel",
    "AlertPreference",
    "RateLimitRule",
    "GeoipSettings",
    "GeoipRule",
    "AnalyticsHourly",
    "AnalyticsDaily",
    "AnalyticsGeo",
    "SystemMetrics",
    "ContainerMetrics",
    "Backup",
    "BackupSettings",
    "UpdateHistory",
    "BaseImageVersion",
    "UpdateSettings",
    "HoneypotTrap",
    "HoneypotHit",
    "IpEnrichment",
]
