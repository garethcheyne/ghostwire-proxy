"""Security presets service — loads and applies best-practice rule templates."""

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.models.waf import WafRule, WafRuleSet, ThreatThreshold
from app.models.rate_limit import GeoipRule, RateLimitRule
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

PRESETS_DIR = Path(__file__).parent.parent / "presets"


def _load_preset_file(filepath: Path) -> dict:
    """Load and parse a single preset JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def list_presets(category: Optional[str] = None) -> list[dict]:
    """List all available presets, optionally filtered by category."""
    presets = []
    if not PRESETS_DIR.exists():
        return presets

    for category_dir in sorted(PRESETS_DIR.iterdir()):
        if not category_dir.is_dir():
            continue
        if category and category_dir.name != category:
            continue

        for preset_file in sorted(category_dir.glob("*.json")):
            try:
                data = _load_preset_file(preset_file)
                # Return summary (without full rule definitions)
                presets.append({
                    "id": data["id"],
                    "name": data["name"],
                    "description": data["description"],
                    "category": data["category"],
                    "severity": data.get("severity", "medium"),
                    "tags": data.get("tags", []),
                    "version": data.get("version", "1.0.0"),
                    "rule_count": len(data.get("rules", data.get("thresholds", []))),
                })
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load preset {preset_file}: {e}")

    return presets


def get_preset(preset_id: str) -> Optional[dict]:
    """Get full preset details including all rules."""
    if not PRESETS_DIR.exists():
        return None

    for category_dir in PRESETS_DIR.iterdir():
        if not category_dir.is_dir():
            continue
        for preset_file in category_dir.glob("*.json"):
            try:
                data = _load_preset_file(preset_file)
                if data.get("id") == preset_id:
                    return data
            except (json.JSONDecodeError, KeyError):
                continue

    return None


async def get_applied_presets(db: AsyncSession) -> set[str]:
    """Return the set of preset_ids currently applied in the database."""
    applied = set()
    for model in (WafRuleSet, WafRule, RateLimitRule, GeoipRule, ThreatThreshold):
        result = await db.execute(
            select(model.preset_id).where(model.preset_id.isnot(None)).distinct()
        )
        applied.update(row[0] for row in result.fetchall())
    return applied


async def is_preset_applied(preset_id: str, db: AsyncSession) -> bool:
    """Check if a preset is already applied by looking for rules tagged with its ID."""
    for model in (WafRuleSet, WafRule, RateLimitRule, GeoipRule, ThreatThreshold):
        result = await db.execute(
            select(func.count()).where(model.preset_id == preset_id)
        )
        if result.scalar() > 0:
            return True
    return False


async def remove_preset(
    preset_id: str,
    db: AsyncSession,
    user_id: str,
    client_ip: Optional[str] = None,
) -> dict:
    """Remove all rules created by a preset."""
    preset = get_preset(preset_id)
    preset_name = preset["name"] if preset else preset_id

    removed = 0
    for model in (WafRule, WafRuleSet, RateLimitRule, GeoipRule, ThreatThreshold):
        result = await db.execute(
            delete(model).where(model.preset_id == preset_id)
        )
        removed += result.rowcount

    db.add(AuditLog(
        action="preset_removed",
        user_id=user_id,
        ip_address=client_ip,
        details=json.dumps({
            "preset_id": preset_id,
            "preset_name": preset_name,
            "items_removed": removed,
        }),
    ))
    await db.commit()

    return {
        "preset_id": preset_id,
        "preset_name": preset_name,
        "items_removed": removed,
    }


async def apply_preset(
    preset_id: str,
    db: AsyncSession,
    user_id: str,
    proxy_host_id: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> dict:
    """Apply a preset — creates rules/settings in the database.

    Returns a summary of what was created.
    """
    preset = get_preset(preset_id)
    if not preset:
        raise ValueError(f"Preset not found: {preset_id}")

    # Check if already applied
    already_applied = await is_preset_applied(preset_id, db)
    if already_applied:
        raise ValueError(f"Preset '{preset['name']}' is already applied. Remove it first to re-apply.")

    category = preset["category"]
    created = []

    if category == "waf":
        created = await _apply_waf_preset(preset, db, preset_id)
    elif category == "geoip":
        created = await _apply_geoip_preset(preset, db, proxy_host_id, preset_id)
    elif category == "rate_limit":
        created = await _apply_rate_limit_preset(preset, db, proxy_host_id, preset_id)
    elif category == "threat_response":
        created = await _apply_threat_response_preset(preset, db, preset_id)
    else:
        raise ValueError(f"Unknown preset category: {category}")

    # Audit log
    db.add(AuditLog(
        action="preset_applied",
        user_id=user_id,
        ip_address=client_ip,
        details=json.dumps({
            "preset_id": preset_id,
            "preset_name": preset["name"],
            "category": category,
            "items_created": len(created),
        }),
    ))
    await db.commit()

    return {
        "preset_id": preset_id,
        "preset_name": preset["name"],
        "category": category,
        "items_created": len(created),
        "items": created,
    }


async def _apply_waf_preset(preset: dict, db: AsyncSession, preset_id: str) -> list[dict]:
    """Apply WAF rule preset — creates a rule set and rules."""
    import uuid

    # Create a rule set for this preset
    rule_set = WafRuleSet(
        id=str(uuid.uuid4()),
        name=f"[Preset] {preset['name']}",
        description=preset["description"],
        enabled=True,
        preset_id=preset_id,
    )
    db.add(rule_set)

    created = []
    for rule_data in preset.get("rules", []):
        rule = WafRule(
            id=str(uuid.uuid4()),
            rule_set_id=rule_set.id,
            name=rule_data["name"],
            description=rule_data.get("description"),
            category=rule_data["category"],
            pattern=rule_data["pattern"],
            severity=rule_data.get("severity", "medium"),
            action=rule_data.get("action", "log"),
            enabled=rule_data.get("enabled", True),
            is_lua=True,
            preset_id=preset_id,
        )
        db.add(rule)
        created.append({"type": "waf_rule", "name": rule.name, "id": rule.id})

    return created


async def _apply_geoip_preset(
    preset: dict, db: AsyncSession, proxy_host_id: Optional[str] = None, preset_id: str = ""
) -> list[dict]:
    """Apply GeoIP rule preset — creates geo blocking rules."""
    import uuid

    created = []
    for rule_data in preset.get("rules", []):
        rule = GeoipRule(
            id=str(uuid.uuid4()),
            proxy_host_id=proxy_host_id,
            name=f"[Preset] {rule_data['name']}",
            mode=rule_data["mode"],
            countries=json.dumps(rule_data["countries"]),
            action=rule_data.get("action", "block"),
            enabled=rule_data.get("enabled", True),
            preset_id=preset_id,
        )
        db.add(rule)
        created.append({"type": "geoip_rule", "name": rule.name, "id": rule.id})

    return created


async def _apply_rate_limit_preset(
    preset: dict, db: AsyncSession, proxy_host_id: Optional[str] = None, preset_id: str = ""
) -> list[dict]:
    """Apply rate limit preset — creates rate limit rules."""
    import uuid

    created = []
    for rule_data in preset.get("rules", []):
        rule = RateLimitRule(
            id=str(uuid.uuid4()),
            proxy_host_id=proxy_host_id,
            name=f"[Preset] {rule_data['name']}",
            requests_per_second=rule_data.get("requests_per_second"),
            requests_per_minute=rule_data.get("requests_per_minute"),
            requests_per_hour=rule_data.get("requests_per_hour"),
            burst_size=rule_data.get("burst_size", 10),
            action=rule_data.get("action", "reject"),
            enabled=rule_data.get("enabled", True),
            preset_id=preset_id,
        )
        db.add(rule)
        created.append({"type": "rate_limit_rule", "name": rule.name, "id": rule.id})

    return created


async def _apply_threat_response_preset(preset: dict, db: AsyncSession, preset_id: str = "") -> list[dict]:
    """Apply threat response preset — creates threat threshold rules."""
    import uuid

    created = []
    for threshold_data in preset.get("thresholds", []):
        threshold = ThreatThreshold(
            id=str(uuid.uuid4()),
            name=f"[Preset] {threshold_data['name']}",
            events_count=threshold_data.get("events_count"),
            time_window_minutes=threshold_data.get("time_window_minutes"),
            threat_score=threshold_data.get("threat_score"),
            response_action=threshold_data["response_action"],
            temp_block_duration_minutes=threshold_data.get("temp_block_duration_minutes"),
            enabled=True,
            priority=threshold_data.get("priority", 0),
            preset_id=preset_id,
        )
        db.add(threshold)
        created.append({"type": "threat_threshold", "name": threshold.name, "id": threshold.id})

    return created
