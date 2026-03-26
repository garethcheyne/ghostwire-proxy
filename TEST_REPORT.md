# Ghostwire Proxy — Test Report

**Date:** 2026-03-26  
**Version:** 2026.03.25.1500  
**Environment:** Docker (ghostwire-proxy-api container)  
**Database:** PostgreSQL 16 (ghostwire_proxy_test)  
**Python:** 3.12.13  
**Next.js:** 16.1.1  

---

## Summary

| Metric | Result |
|--------|--------|
| **Total Tests** | 227 |
| **Passed** | 223 |
| **Failed** | 1 |
| **Skipped** | 3 |
| **Duration** | 40.09s |
| **Pass Rate** | 98.2% |

---

## Backend Test Results (pytest)

### Alert Service — 15/15 passed
| Test | Status |
|------|--------|
| test_dispatch_with_no_preferences | PASSED |
| test_dispatch_skips_low_severity | PASSED |
| test_dispatch_disabled_preference_skipped | PASSED |
| test_send_to_webhook_channel | PASSED |
| test_send_to_email_channel | PASSED |
| test_send_to_unknown_channel | PASSED |
| test_webhook_success | PASSED |
| test_webhook_no_url | PASSED |
| test_webhook_exception | PASSED |
| test_slack_no_webhook_url | PASSED |
| test_slack_success | PASSED |
| test_telegram_no_token | PASSED |
| test_telegram_no_chat_id | PASSED |
| test_telegram_success | PASSED |
| test_email_always_returns_true | PASSED |

### Analytics Service — 3/3 passed
| Test | Status |
|------|--------|
| test_aggregate_no_data (hourly) | PASSED |
| test_aggregate_hourly_returns_int | PASSED |
| test_aggregate_no_data (geo) | PASSED |

### Backup Service — 6/6 passed
| Test | Status |
|------|--------|
| test_list_backups_empty | PASSED |
| test_get_backup_not_found | PASSED |
| test_delete_backup_not_found | PASSED |
| test_create_backup | PASSED |
| test_get_settings_returns_defaults | PASSED |
| test_update_settings | PASSED |

### Certificate Service — 11/11 passed
| Test | Status |
|------|--------|
| test_cert_not_found | PASSED |
| test_not_letsencrypt_cert | PASSED |
| test_certbot_success | PASSED |
| test_certbot_failure | PASSED |
| test_certbot_timeout | PASSED |
| test_renew_not_found | PASSED |
| test_renew_not_letsencrypt | PASSED |
| test_renew_success | PASSED |
| test_no_expiring_certs | PASSED |
| test_find_expiring_cert | PASSED |
| test_non_expiring_cert_not_included | PASSED |

### Cloudflare Service — 5/5 passed
| Test | Status |
|------|--------|
| test_verify_token_success | PASSED |
| test_verify_token_failure | PASSED |
| test_list_zones_success | PASSED |
| test_create_dns_record_success | PASSED |
| test_delete_dns_record_success | PASSED |

### Dependency Injection (deps) — 7/7 passed
| Test | Status |
|------|--------|
| test_valid_token_returns_user | PASSED |
| test_invalid_token_raises | PASSED |
| test_refresh_token_rejected | PASSED |
| test_deleted_user_raises | PASSED |
| test_inactive_user_raises | PASSED |
| test_admin_user_passes | PASSED |
| test_non_admin_raises | PASSED |

### Firewall Service — 15/16 (1 failed)
| Test | Status |
|------|--------|
| test_get_routeros_connector | PASSED |
| test_get_unifi_connector | PASSED |
| test_get_pfsense_connector | PASSED |
| test_get_opnsense_connector | PASSED |
| test_get_unknown_connector | PASSED |
| test_test_connection_success (RouterOS) | PASSED |
| test_test_connection_failure (RouterOS) | PASSED |
| test_test_connection_exception (RouterOS) | PASSED |
| test_add_to_blocklist_success (RouterOS) | PASSED |
| test_test_connection_success_with_findings (UniFi) | PASSED |
| test_test_connection_missing_ipv6_list (UniFi) | PASSED |
| test_test_connection_invalid_api_key (UniFi) | PASSED |
| test_add_ipv4_to_blocklist (UniFi) | PASSED |
| **test_add_ipv6_to_blocklist (UniFi)** | **FAILED** |
| test_remove_from_blocklist_success (UniFi) | PASSED |
| test_is_ipv6 | PASSED |

> **Failure:** `test_add_ipv6_to_blocklist` — `TypeError: 'NoneType' object is not subscriptable`  
> The test assertion at line 441 expects a specific mock call structure that doesn't match the current IPv6 blocklist implementation. Pre-existing issue from the IPv4/IPv6 split refactor.

### Models — 14/14 passed
| Test | Status |
|------|--------|
| test_create_user | PASSED |
| test_user_defaults | PASSED |
| test_create_audit_log | PASSED |
| test_create_setting | PASSED |
| test_create_rate_limit_rule | PASSED |
| test_create_waf_rule_set | PASSED |
| test_create_waf_rule | PASSED |
| test_create_threat_actor | PASSED |
| test_create_threat_threshold | PASSED |
| test_create_certificate | PASSED |
| test_create_proxy_host | PASSED |
| test_create_access_list | PASSED |
| test_create_traffic_log | PASSED |
| test_create_alert_channel | PASSED |

### OpenResty Service — 10/10 passed
| Test | Status |
|------|--------|
| test_nginx_config | PASSED |
| test_empty_upstream_returns_empty | PASSED |
| test_upstream_with_servers | PASSED |
| test_http_server_block | PASSED |
| test_ssl_server_block | PASSED |
| test_multiple_domains | PASSED |
| test_default_congratulations | PASSED |
| test_redirect_behavior | PASSED |
| test_404_behavior | PASSED |
| test_444_drop_behavior | PASSED |

### Per-Host Features — 10/10 passed
| Test | Status |
|------|--------|
| test_create_waf_rule_global | PASSED |
| test_create_waf_rule_per_host | PASSED |
| test_list_waf_rules_filter_by_host | PASSED |
| test_create_rate_limit_with_host | PASSED |
| test_list_rate_limits_filter_by_host | PASSED |
| test_create_geoip_rule_with_host | PASSED |
| test_list_geoip_rules_filter_by_host | PASSED |
| test_create_trap_global | PASSED |
| test_create_trap_per_host | PASSED |
| test_duplicate_trap_same_host_rejected | PASSED |

### Preset Service — 16/16 (3 skipped)
| Test | Status |
|------|--------|
| test_list_all_presets | PASSED |
| test_preset_has_required_fields | PASSED |
| test_filter_by_waf_category | PASSED |
| test_filter_by_geoip_category | PASSED |
| test_filter_by_rate_limit_category | PASSED |
| test_filter_by_threat_response_category | PASSED |
| test_filter_nonexistent_category | PASSED |
| test_presets_have_valid_severity | PASSED |
| test_presets_have_positive_rule_count | PASSED |
| test_list_presets_no_dir | PASSED |
| test_get_existing_preset | PASSED |
| test_get_nonexistent_preset | PASSED |
| test_get_preset_has_rules | PASSED |
| test_apply_waf_preset | PASSED |
| test_apply_geoip_preset | PASSED |
| test_apply_rate_limit_preset | SKIPPED |
| test_apply_threat_response_preset | SKIPPED |
| test_apply_preset_with_proxy_host_id | SKIPPED |

### Routes: Auth — 11/11 passed
| Test | Status |
|------|--------|
| test_login_success | PASSED |
| test_login_wrong_password | PASSED |
| test_login_nonexistent_user | PASSED |
| test_login_disabled_user | PASSED |
| test_login_invalid_email_format | PASSED |
| test_refresh_success | PASSED |
| test_refresh_invalid_token | PASSED |
| test_refresh_with_access_token_fails | PASSED |
| test_refresh_disabled_user | PASSED |
| test_me_authenticated | PASSED |
| test_me_no_auth | PASSED |

### Routes: Presets — 6/6 passed
| Test | Status |
|------|--------|
| test_list_presets | PASSED |
| test_list_presets_filter_category | PASSED |
| test_list_presets_no_auth | PASSED |
| test_get_preset | PASSED |
| test_apply_preset | PASSED |
| test_apply_nonexistent_preset | PASSED |

### Routes: Rate Limits & GeoIP — 8/8 passed
| Test | Status |
|------|--------|
| test_list_rate_limits | PASSED |
| test_create_rate_limit | PASSED |
| test_get_rate_limit | PASSED |
| test_delete_rate_limit | PASSED |
| test_rate_limits_no_auth | PASSED |
| test_get_geoip_settings | PASSED |
| test_list_geoip_rules | PASSED |
| test_create_geoip_rule | PASSED |

### Routes: Settings — 6/6 passed
| Test | Status |
|------|--------|
| test_get_all_settings | PASSED |
| test_get_settings_no_auth | PASSED |
| test_get_specific_setting | PASSED |
| test_update_setting | PASSED |
| test_get_default_site_via_key | PASSED |
| test_update_default_site | PASSED |

### Routes: System — 5/5 passed
| Test | Status |
|------|--------|
| test_get_system_status | PASSED |
| test_system_status_no_auth | PASSED |
| test_get_metrics | PASSED |
| test_get_metrics_invalid_period | PASSED |
| test_get_throughput | PASSED |

### Routes: Users — 7/7 passed
| Test | Status |
|------|--------|
| test_list_users | PASSED |
| test_list_users_no_auth | PASSED |
| test_create_user | PASSED |
| test_create_duplicate_email | PASSED |
| test_get_user | PASSED |
| test_update_user_name | PASSED |
| test_delete_user | PASSED |

### Security — 15/15 passed
| Test | Status |
|------|--------|
| test_hash_password | PASSED |
| test_verify_correct_password | PASSED |
| test_verify_wrong_password | PASSED |
| test_different_hashes_for_same_password | PASSED |
| test_truncate_short_password | PASSED |
| test_truncate_long_password | PASSED |
| test_empty_password | PASSED |
| test_create_access_token | PASSED |
| test_decode_access_token | PASSED |
| test_create_refresh_token | PASSED |
| test_access_token_with_custom_expiry | PASSED |
| test_decode_invalid_token | PASSED |
| test_decode_empty_token | PASSED |
| test_encrypt_and_decrypt | PASSED |
| test_encrypt_produces_different_ciphertext | PASSED |

### Session Service — 6/6 passed
| Test | Status |
|------|--------|
| test_create_session | PASSED |
| test_validate_session | PASSED |
| test_validate_invalid_session | PASSED |
| test_revoke_session | PASSED |
| test_get_active_session_count | PASSED |
| test_get_cookie_header | PASSED |

### System Service — 3/3 passed
| Test | Status |
|------|--------|
| test_get_system_status | PASSED |
| test_get_metrics_history | PASSED |
| test_get_traffic_throughput | PASSED |

### Threat Service — 6/6 passed
| Test | Status |
|------|--------|
| test_record_new_event | PASSED |
| test_record_event_creates_actor | PASSED |
| test_record_event_increments_actor_score | PASSED |
| test_unblocked_ip | PASSED |
| test_blocked_ip | PASSED |
| test_monitored_ip_not_blocked | PASSED |

---

## Frontend Build

| Check | Result |
|-------|--------|
| Next.js Build | Compiled successfully |
| Build ID | `40WUfp1O8uYcDsgbLo7-F` |
| Container Status | Healthy |
| TypeScript | No errors |

---

## Container Health

| Container | Status |
|-----------|--------|
| ghostwire-proxy-ui | Up ~1 hour (healthy) |
| ghostwire-proxy-api | Up ~2 hours (healthy) |
| ghostwire-proxy-nginx | Up 28 hours (healthy) |
| ghostwire-proxy-postgres | Up 2 days (healthy) |
| ghostwire-proxy-redis | Up 2 days (healthy) |
| ghostwire-proxy-updater | Up 28 hours (healthy) |
| ghostwire-proxy-certbot | Up 28 hours |

---

## Infrastructure Changes

### Test Database Upgrade: SQLite → PostgreSQL
- **conftest.py** now uses `postgresql+asyncpg` instead of `sqlite+aiosqlite`
- Created dedicated `ghostwire_proxy_test` database in the Docker Postgres container
- Tests run inside the `ghostwire-proxy-api` container for direct DB access
- Eliminated SQLite/Postgres behavioral differences in test results

---

## Known Issues

1. **`test_add_ipv6_to_blocklist`** — Mock assertion doesn't match refactored UniFi IPv6 API call structure. Needs test update to align with the IPv4/IPv6 split.

2. **3 skipped tests** — `test_apply_rate_limit_preset`, `test_apply_threat_response_preset`, `test_apply_preset_with_proxy_host_id` — awaiting implementation of preset apply logic for those categories.

3. **Pydantic v2 deprecation warnings (33)** — `class Config` usage should be migrated to `model_config = ConfigDict(...)`. Non-breaking, cosmetic.
