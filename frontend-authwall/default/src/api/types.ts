export interface AuthProvider {
  id: string
  name: string
  provider_type: 'google' | 'github' | 'azure_ad' | 'oidc'
  enabled: boolean
}

export interface AuthWallConfig {
  id: string
  name: string
  auth_type: 'basic' | 'oauth' | 'ldap' | 'multi'
  session_timeout: number
  theme?: string
  providers: AuthProvider[]
  has_local_users: boolean
  has_ldap: boolean
}

export interface LoginResponse {
  success: boolean
  message?: string
  requires_totp?: boolean
  partial_session_id?: string
  redirect_url?: string
}

export interface TotpResponse {
  success: boolean
  message?: string
  redirect_url?: string
}
