'use client'

import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useCertificates } from '@/lib/queries/dashboard'
import { certificateKeys } from '@/lib/queries/keys'
import { toastSuccess, toastError } from '@/lib/toast'
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
  X,
} from 'lucide-react'
import api from '@/lib/api'
import { Textarea } from '@/components/ui/textarea'
import { Modal, ModalBody } from '@/components/ui/modal'
import { useConfirm } from '@/components/confirm-dialog'
import type { Certificate } from '@/types'
import { PageHeader } from '@/components/page-header'
import { Shield as HeaderIcon } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ContentSkeleton, LoadError } from '@/components/load-state'

export default function CertificatesPage() {
  const confirm = useConfirm()
  const queryClient = useQueryClient()
  const { data: certificatesData, isPending, isError, refetch } = useCertificates({ limit: 100 })
  const certificates: Certificate[] = certificatesData?.items ?? []
  const isLoading = isPending
  const fetchCertificates = () =>
    queryClient.invalidateQueries({ queryKey: certificateKeys.all })
  // One clock reading per visit: expiry is counted in whole days, and reading the clock while
  // rendering would give a different answer on every re-render.
  const [now] = useState(() => Date.now())
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [createMode, setCreateMode] = useState<'upload' | 'letsencrypt'>('letsencrypt')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

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
      toastSuccess(createMode === 'letsencrypt' ? "Let's Encrypt certificate requested" : 'Certificate uploaded successfully')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create certificate')
      toastError('Failed to create certificate')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleRenew = async (cert: Certificate) => {
    try {
      await api.post(`/api/certificates/${cert.id}/renew`)
      fetchCertificates()
      toastSuccess('Certificate renewal initiated')
    } catch (error) {
      console.error('Failed to renew certificate:', error)
      toastError('Failed to renew certificate')
    }
  }

  const handleDelete = async (cert: Certificate) => {
    if (!(await confirm({ description: `Are you sure you want to delete "${cert.name}"?`, variant: 'destructive' }))) return

    try {
      await api.delete(`/api/certificates/${cert.id}`)
      fetchCertificates()
      toastSuccess('Certificate deleted')
    } catch (error) {
      console.error('Failed to delete certificate:', error)
      toastError('Failed to delete certificate')
    }
  }

  const getDaysUntilExpiry = (expiresAt: string | null) => {
    if (!expiresAt) return null
    return Math.floor(
      (new Date(expiresAt).getTime() - now) / (1000 * 60 * 60 * 24)
    )
  }

  const getStatusColor = (status: string, daysUntilExpiry: number | null) => {
    if (status === 'error') return 'text-red-600 dark:text-red-400'
    if (status === 'pending') return 'text-yellow-700 dark:text-yellow-400'
    if (daysUntilExpiry !== null && daysUntilExpiry <= 7) return 'text-red-600 dark:text-red-400'
    if (daysUntilExpiry !== null && daysUntilExpiry <= 30) return 'text-yellow-700 dark:text-yellow-400'
    return 'text-green-600 dark:text-green-400'
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={HeaderIcon}
        title="SSL Certificates"
        description="Manage SSL/TLS certificates for your proxy hosts"
        actions={
          <>
            <Button
              size="lg"
              onClick={() => {
                resetForm()
                setShowCreateDialog(true)
              }}
            >
              <Plus className="h-4 w-4" />
              Add Certificate
            </Button>
          </>
        }
      />

      {/* Certificates Grid */}
      {isLoading ? (
        <ContentSkeleton rows={3} />
      ) : isError ? (
        <LoadError what="certificates" onRetry={() => refetch()} />
      ) : (
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
                      <AlertTriangle className="h-5 w-5 text-red-600 dark:text-red-400" />
                    ) : (
                      <Clock className="h-5 w-5 text-yellow-700 dark:text-yellow-400" />
                    )}
                    <div>
                      <h3 className="font-semibold" data-private="domain">{cert.name}</h3>
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          cert.is_letsencrypt
                            ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                            : 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                        }`}
                      >
                        {cert.is_letsencrypt ? "Let's Encrypt" : 'Custom'}
                      </span>
                    </div>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-xs" aria-label="Actions">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                      {cert.is_letsencrypt && (
                        <DropdownMenuItem
                          onSelect={() => handleRenew(cert)}
                          className="gap-2"
                        >
                          <RefreshCw className="h-4 w-4" />
                          Renew
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuItem
                        onSelect={() => handleDelete(cert)}
                        className="gap-2 text-red-600 dark:text-red-400 focus:text-red-500"
                      >
                        <Trash2 className="h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                <div className="space-y-2 text-sm">
                  <div>
                    <p className="text-muted-foreground">Domains</p>
                    <p className="font-mono text-xs" data-private="domain">
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
      )}

      {/* Create Dialog */}
      <Modal
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
        size="lg"
        srTitle="Certificates — Create"
      >
        <ModalBody className="p-0">
            <div className="border-b border-border p-6">
              <h2 className="text-xl font-semibold">Add Certificate</h2>
            </div>

            {/* Mode Tabs */}
            <div className="border-b border-border px-6 py-4">
              <Tabs value={createMode} onValueChange={(v) => setCreateMode(v as typeof createMode)}>
                <TabsList>
                  <TabsTrigger value="letsencrypt">
                    <RefreshCw />
                    Let&apos;s Encrypt
                  </TabsTrigger>
                  <TabsTrigger value="upload">
                    <Upload />
                    Upload Custom
                  </TabsTrigger>
                </TabsList>
              </Tabs>
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
                        className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
                        placeholder="example.com"
                      />
                      <Button
                        variant="outline"
                        size="lg"
                        type="button"
                        onClick={handleAddLeDomain}
                      >
                        Add
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {leDomains.map((domain) => (
                        <span
                          key={domain}
                          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-sm text-primary"
                        >
                          {domain}
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            type="button"
                            onClick={() => handleRemoveLeDomain(domain)}
                            className="-mr-1.5 size-5 text-primary hover:bg-primary/10 hover:text-primary"
                            aria-label={`Remove ${domain}`}
                          >
                            <X />
                          </Button>
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
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
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
                      className="w-full px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
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
                        className="flex-1 px-4 py-2 rounded-lg border border-input bg-background focus:outline-hidden focus:ring-2 focus:ring-primary"
                        placeholder="example.com"
                      />
                      <Button
                        variant="outline"
                        size="lg"
                        type="button"
                        onClick={handleAddUploadDomain}
                      >
                        Add
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {uploadDomains.map((domain) => (
                        <span
                          key={domain}
                          className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-3 py-1 text-sm text-primary"
                        >
                          {domain}
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            type="button"
                            onClick={() => handleRemoveUploadDomain(domain)}
                            className="-mr-1.5 size-5 text-primary hover:bg-primary/10 hover:text-primary"
                            aria-label={`Remove ${domain}`}
                          >
                            <X />
                          </Button>
                        </span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Certificate (PEM)
                    </label>
                    <Textarea
                      value={uploadCert}
                      onChange={(e) => setUploadCert(e.target.value)}
                      className="w-full rounded-lg bg-background font-mono text-xs"
                      rows={6}
                      placeholder="-----BEGIN CERTIFICATE-----"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Private Key (PEM)
                    </label>
                    <Textarea
                      value={uploadKey}
                      onChange={(e) => setUploadKey(e.target.value)}
                      className="w-full rounded-lg bg-background font-mono text-xs"
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
                <Button
                  variant="outline"
                  size="lg"
                  type="button"
                  onClick={() => setShowCreateDialog(false)}
                >
                  Cancel
                </Button>
                <Button
                  size="lg"
                  type="submit"
                  disabled={isSubmitting}
                >
                  {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  {createMode === 'letsencrypt' ? 'Request Certificate' : 'Upload'}
                </Button>
              </div>
            </form>
        </ModalBody>
      </Modal>

    </div>
  )
}
