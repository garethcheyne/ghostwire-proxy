// User types
export interface User {
  id: string
  email: string
  name: string
  role: string
  is_active: boolean
  signin_count: number
  last_signin_at: string | null
  created_at: string
  updated_at: string
}

// Proxy Host types
export interface UpstreamServer {
  id: string
  proxy_host_id: string
  host: string
  port: number
  weight: number
  max_fails: number
  fail_timeout: number
  enabled: boolean
  created_at: string
}

export interface ProxyLocation {
  id: string
  proxy_host_id: string
  path: string
  match_type: 'prefix' | 'exact' | 'regex' | 'regex_case_insensitive'
  priority: number
  forward_scheme: 'http' | 'https'
  forward_host: string
  forward_port: number
  websockets_support: boolean
  cache_enabled: boolean
  cache_valid: string | null
  cache_bypass: string | null
  rate_limit_enabled: boolean
  rate_limit_requests: number
  rate_limit_period: string
  rate_limit_burst: number
  custom_headers: Record<string, string> | null
  proxy_headers: Record<string, string> | null
  hide_headers: string[] | null
  proxy_connect_timeout: number
  proxy_send_timeout: number
  proxy_read_timeout: number
  advanced_config: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface ProxyHost {
  id: string
  domain_names: string[]
  forward_scheme: 'http' | 'https'
  forward_host: string
  forward_port: number
  ssl_enabled: boolean
  ssl_force: boolean
  certificate_id: string | null
  http2_support: boolean
  hsts_enabled: boolean
  hsts_subdomains: boolean
  websockets_support: boolean
  block_exploits: boolean
  access_list_id: string | null
  auth_wall_id: string | null
  // Location-level advanced config
  advanced_config: string | null
  // Server-level advanced config
  server_advanced_config: string | null
  // Server-level settings
  client_max_body_size: string
  proxy_buffering: boolean
  proxy_buffer_size: string
  proxy_buffers: string
  // Caching
  cache_enabled: boolean
  cache_valid: string | null
  cache_bypass: string | null
  // Rate limiting
  rate_limit_enabled: boolean
  rate_limit_requests: number
  rate_limit_period: string
  rate_limit_burst: number
  // Custom error pages
  custom_error_pages: Record<string, string> | null
  traffic_logging_enabled: boolean
  enabled: boolean
  upstream_servers: UpstreamServer[]
  locations: ProxyLocation[]
  created_at: string
  updated_at: string
}

// Certificate types
export interface Certificate {
  id: string
  name: string
  domain_names: string[]
  is_letsencrypt: boolean
  letsencrypt_email: string | null
  expires_at: string | null
  auto_renew: boolean
  status: 'pending' | 'valid' | 'expired' | 'error'
  last_renewed_at: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

// Access List types
export interface AccessListEntry {
  id: string
  access_list_id: string
  ip_or_cidr: string
  action: 'allow' | 'deny'
  description: string | null
  created_at: string
}

export interface AccessList {
  id: string
  name: string
  mode: 'whitelist' | 'blacklist'
  default_action: 'allow' | 'deny'
  entries: AccessListEntry[]
  created_at: string
  updated_at: string
}

// Auth Wall types
export interface LocalAuthUser {
  id: string
  auth_wall_id: string
  username: string
  display_name: string | null
  email: string | null
  is_active: boolean
  totp_enabled: boolean
  totp_verified: boolean
  failed_attempts: number
  locked_until: string | null
  created_at: string
  updated_at: string
}

export interface AuthProvider {
  id: string
  auth_wall_id: string
  name: string
  provider_type: 'google' | 'github' | 'azure_ad' | 'oidc'
  client_id: string | null
  authorization_url: string | null
  token_url: string | null
  userinfo_url: string | null
  scopes: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface LdapConfig {
  id: string
  auth_wall_id: string
  name: string
  host: string
  port: number
  use_ssl: boolean
  use_starttls: boolean
  bind_dn: string | null
  base_dn: string
  user_filter: string
  username_attribute: string
  email_attribute: string | null
  display_name_attribute: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface AuthWall {
  id: string
  name: string
  auth_type: 'basic' | 'oauth' | 'ldap' | 'multi'
  session_timeout: number
  theme: string
  default_provider_id: string | null
  local_users: LocalAuthUser[]
  providers: AuthProvider[]
  ldap_config: LdapConfig | null
  created_at: string
  updated_at: string
}

// Traffic types
export interface TrafficLog {
  id: string
  proxy_host_id: string
  host_name: string | null
  timestamp: string
  client_ip: string
  request_method: string
  request_uri: string
  query_string: string | null
  status: number
  response_time: number | null
  bytes_sent: number | null
  bytes_received: number | null
  upstream_addr: string | null
  upstream_response_time: number | null
  ssl_protocol: string | null
  ssl_cipher: string | null
  user_agent: string | null
  referer: string | null
  country_code: string | null
  country_name: string | null
  auth_user: string | null
}

export interface TrafficStats {
  total_requests: number
  requests_today: number
  requests_this_week: number
  requests_by_status: Record<string, number>
  requests_by_method: Record<string, number>
  avg_response_time: number | null
  total_bytes_sent: number
  total_bytes_received: number
  top_ips: { ip: string; count: number }[]
  top_hosts: { host_id: string; name: string; count: number }[]
}

// Settings
export interface Setting {
  key: string
  value: string | null
  description: string | null
  updated_at: string
}

// DNS Provider types
export interface DnsProvider {
  id: string
  name: string
  provider_type: 'cloudflare' | 'godaddy' | 'route53'
  api_key: string | null
  api_secret: string | null
  zone_id: string | null
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface DnsRecord {
  id: string
  type: 'A' | 'AAAA' | 'CNAME' | 'TXT' | 'MX'
  name: string
  content: string
  ttl: number
  proxied: boolean
}

// Dashboard stats
export interface DashboardStats {
  total_hosts: number
  active_hosts: number
  total_certificates: number
  expiring_certificates: number
  requests_today: number
  blocked_requests: number
  total_traffic_bytes: number
}
