'use client'

import { useState, useEffect } from 'react'
import {
  Shield,
  Plus,
  MoreHorizontal,
  Trash2,
  RefreshCw,
  Download,
  Upload,
  Loader2,
  CheckCircle,
  AlertTriangle,
  Clock,
} from 'lucide-react'
import api from '@/lib/api'
import type { Certificate } from '@/types'

export default function CertificatesPage() {
  const [certificates, setCertificates] = useState<Certificate[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [createMode, setCreateMode] = useState<'upload' | 'letsencrypt'>('letsencrypt')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)

  // Let's Encrypt form
  const [leDomains, setLeDomains] = useState<string[]>([])
  const [leDomainInput, setLeDomainInput] = useState('')
  const [leEmail, setLeEmail] = useState('')

  // Upload form
  const [uploadName, setUploadName] = useState('')
  const [uploadDomains, setUploadDomains] = useState<string[]>([])
  const [uploadDomainInput, setUploadDomainInput] = useState('')
  const [uploadCert, setUploadCert] = useState('')
  const [uploadKey, setUploadKey] = useState('')

  useEffect(() => {
    fetchCertificates()
  }, [])

  const fetchCertificates = async () => {
    try {
      const response = await api.get('/api/certificates')
      setCertificates(response.data)
    } catch (error) {
      console.error('Failed to fetch certificates:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const resetForm = () => {
    setLeDomains([])
    setLeDomainInput('')
    setLeEmail('')
    setUploadName('')
    setUploadDomains([])
    setUploadDomainInput('')
    setUploadCert('')
    setUploadKey('')
    setError('')
  }

  const handleAddUploadDomain = () => {
    if (uploadDomainInput.trim() && !uploadDomains.includes(uploadDomainInput.trim())) {
      setUploadDomains([...uploadDomains, uploadDomainInput.trim()])
      setUploadDomainInput('')
    }
  }

  const handleRemoveUploadDomain = (domain: string) => {
    setUploadDomains(uploadDomains.filter((d) => d !== domain))
  }

  const handleAddLeDomain = () => {
    if (leDomainInput.trim() && !leDomains.includes(leDomainInput.trim())) {
      setLeDomains([...leDomains, leDomainInput.trim()])
      setLeDomainInput('')
    }
  }

  const handleRemoveLeDomain = (domain: string) => {
    setLeDomains(leDomains.filter((d) => d !== domain))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      if (createMode === 'letsencrypt') {
        if (leDomains.length === 0) {
          setError('At least one domain is required')
          setIsSubmitting(false)
          return
        }
        // Auto-generate name from first domain
        const certName = leDomains[0].replace(/^\*\./, 'wildcard.')
        await api.post('/api/certificates/letsencrypt', {
          name: certName,
          domain_names: leDomains,
          email: leEmail,
        })
      } else {
        if (!uploadName || !uploadCert || !uploadKey || uploadDomains.length === 0) {
          setError('All fields are required including at least one domain')
          setIsSubmitting(false)
          return
        }
        await api.post('/api/certificates', {
          name: uploadName,
          domain_names: uploadDomains,
          certificate: uploadCert,
          certificate_key: uploadKey,
        })
      }

      setShowCreateDialog(false)
      resetForm()
      fetchCertificates()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create certificate')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleRenew = async (cert: Certificate) => {
    try {
      await api.post(`/api/certificates/${cert.id}/renew`)
      fetchCertificates()
    } catch (error) {
      console.error('Failed to renew certificate:', error)
    }
    setActiveDropdown(null)
  }

  const handleDelete = async (cert: Certificate) => {
    if (!confirm(`Are you sure you want to delete "${cert.name}"?`)) {
      return
    }

    try {
      await api.delete(`/api/certificates/${cert.id}`)
      fetchCertificates()
    } catch (error) {
      console.error('Failed to delete certificate:', error)
    }
    setActiveDropdown(null)
  }

  const getDaysUntilExpiry = (expiresAt: string | null) => {
    if (!expiresAt) return null
    return Math.floor(
      (new Date(expiresAt).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    )
  }

  const getStatusColor = (status: string, daysUntilExpiry: number | null) => {
    if (status === 'error') return 'text-red-500'
    if (status === 'pending') return 'text-yellow-500'
    if (daysUntilExpiry !== null && daysUntilExpiry <= 7) return 'text-red-500'
    if (daysUntilExpiry !== null && daysUntilExpiry <= 30) return 'text-yellow-500'
    return 'text-green-500'
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading certificates...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">SSL Certificates</h1>
          <p className="text-muted-foreground">
            Manage SSL/TLS certificates for your proxy hosts
          </p>
        </div>
        <button
          onClick={() => {
            resetForm()
            setShowCreateDialog(true)
          }}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          Add Certificate
        </button>
      </div>

      {/* Certificates Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {certificates.length === 0 ? (
          <div className="col-span-full rounded-xl border border-border bg-card p-12 text-center">
            <Shield className="mx-auto h-12 w-12 mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground">No certificates configured</p>
            <p className="text-sm text-muted-foreground mt-1">
              Click "Add Certificate" to create one
            </p>
          </div>
        ) : (
          certificates.map((cert) => {
            const daysUntilExpiry = getDaysUntilExpiry(cert.expires_at)
            const statusColor = getStatusColor(cert.status, daysUntilExpiry)

            return (
              <div key={cert.id} className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    {cert.status === 'valid' ? (
                      <CheckCircle className={`h-5 w-5 ${statusColor}`} />
                    ) : cert.status === 'error' ? (
                      <AlertTriangle className="h-5 w-5 text-red-500" />
                    ) : (
                      <Clock className="h-5 w-5 text-yellow-500" />
                    )}
                    <div>
                      <h3 className="font-semibold">{cert.name}</h3>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          cert.is_letsencrypt
                            ? 'bg-green-500/10 text-green-500'
                            : 'bg-blue-500/10 text-blue-500'
                        }`}
                      >
                        {cert.is_letsencrypt ? "Let's Encrypt" : 'Custom'}
                      </span>
                    </div>
                  </div>
                  <div className="relative">
                    <button
                      onClick={() =>
                        setActiveDropdown(activeDropdown === cert.id ? null : cert.id)
                      }
                      className="rounded-lg p-1 hover:bg-muted"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>

                    {activeDropdown === cert.id && (
                      <div className="absolute right-0 top-full z-10 mt-1 w-40 rounded-lg border border-border bg-card shadow-lg">
                        <div className="p-1">
                          {cert.is_letsencrypt && (
                            <button
                              onClick={() => handleRenew(cert)}
                              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-muted"
                            >
                              <RefreshCw className="h-4 w-4" />
                              Renew
                            </button>
                          )}
                          <button
                            onClick={() => handleDelete(cert)}
                            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-red-500 hover:bg-muted"
                          >
                            <Trash2 className="h-4 w-4" />
                            Delete
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="space-y-2 text-sm">
                  <div>
                    <p className="text-muted-foreground">Domains</p>
                    <p className="font-mono text-xs">
                      {cert.domain_names.slice(0, 2).join(', ')}
                      {cert.domain_names.length > 2 && (
                        <span className="text-muted-foreground">
                          {' '}+{cert.domain_names.length - 2} more
                        </span>
                      )}
                    </p>
                  </div>
                  {cert.expires_at && (
                    <div>
                      <p className="text-muted-foreground">Expires</p>
                      <p className={statusColor}>
                        {new Date(cert.expires_at).toLocaleDateString()}
                        {daysUntilExpiry !== null && (
                          <span className="ml-1">({daysUntilExpiry} days)</span>
                        )}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Create Dialog */}
      {showCreateDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-card border border-border shadow-xl">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">Add Certificate</h2>
            </div>

            {/* Mode Tabs */}
            <div className="flex border-b border-border">
              <button
                onClick={() => setCreateMode('letsencrypt')}
                className={`flex-1 px-4 py-3 text-sm font-medium ${
                  createMode === 'letsencrypt'
                    ? 'border-b-2 border-primary text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <div className="flex items-center justify-center gap-2">
                  <RefreshCw className="h-4 w-4" />
                  Let's Encrypt
                </div>
              </button>
              <button
                onClick={() => setCreateMode('upload')}
                className={`flex-1 px-4 py-3 text-sm font-medium ${
                  createMode === 'upload'
                    ? 'border-b-2 border-primary text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <div className="flex items-center justify-center gap-2">
                  <Upload className="h-4 w-4" />
                  Upload Custom
                </div>
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {createMode === 'letsencrypt' ? (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Domain Names
                    </label>
                    <div className="flex gap-2 mb-2">
                      <input
                        type="text"
                        value={leDomainInput}
                        onChange={(e) => setLeDomainInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            handleAddLeDomain()
                          }
                        }}
                        className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                        placeholder="example.com"
                      />
                      <button
                        type="button"
                        onClick={handleAddLeDomain}
                        className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                      >
                        Add
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {leDomains.map((domain) => (
                        <span
                          key={domain}
                          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-sm text-primary"
                        >
                          {domain}
                          <button
                            type="button"
                            onClick={() => handleRemoveLeDomain(domain)}
                            className="hover:text-primary/70"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Email Address
                    </label>
                    <input
                      type="email"
                      value={leEmail}
                      onChange={(e) => setLeEmail(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder="admin@example.com"
                      required
                    />
                    <p className="mt-1 text-xs text-muted-foreground">
                      Used for expiration notifications from Let's Encrypt
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Certificate Name
                    </label>
                    <input
                      type="text"
                      value={uploadName}
                      onChange={(e) => setUploadName(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                      placeholder="My Certificate"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Domain Names
                    </label>
                    <div className="flex gap-2 mb-2">
                      <input
                        type="text"
                        value={uploadDomainInput}
                        onChange={(e) => setUploadDomainInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault()
                            handleAddUploadDomain()
                          }
                        }}
                        className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary"
                        placeholder="example.com"
                      />
                      <button
                        type="button"
                        onClick={handleAddUploadDomain}
                        className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                      >
                        Add
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {uploadDomains.map((domain) => (
                        <span
                          key={domain}
                          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-sm text-primary"
                        >
                          {domain}
                          <button
                            type="button"
                            onClick={() => handleRemoveUploadDomain(domain)}
                            className="hover:text-primary/70"
                          >
                            ×
                          </button>
                        </span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Certificate (PEM)
                    </label>
                    <textarea
                      value={uploadCert}
                      onChange={(e) => setUploadCert(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary font-mono text-xs"
                      rows={6}
                      placeholder="-----BEGIN CERTIFICATE-----"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Private Key (PEM)
                    </label>
                    <textarea
                      value={uploadKey}
                      onChange={(e) => setUploadKey(e.target.value)}
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-none focus:ring-2 focus:ring-primary font-mono text-xs"
                      rows={6}
                      placeholder="-----BEGIN PRIVATE KEY-----"
                      required
                    />
                  </div>
                </>
              )}

              {error && (
                <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                  {error}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setShowCreateDialog(false)}
                  className="px-4 py-2 rounded-lg border border-input hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  {createMode === 'letsencrypt' ? 'Request Certificate' : 'Upload'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Click outside to close dropdown */}
      {activeDropdown && (
        <div
          className="fixed inset-0 z-0"
          onClick={() => setActiveDropdown(null)}
        />
      )}
    </div>
  )
}
