import { useState, useRef, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { ShieldCheck, ArrowLeft, Loader2, AlertCircle, Key } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { verifyTotp } from '@/api/client'

export default function Totp() {
  const [searchParams] = useSearchParams()
  const wallId = searchParams.get('wall') || ''
  const sessionId = searchParams.get('session') || ''
  const redirectUrl = searchParams.get('redirect') || '/'

  const [code, setCode] = useState(['', '', '', '', '', ''])
  const [isBackupMode, setIsBackupMode] = useState(false)
  const [backupCode, setBackupCode] = useState('')
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  // Auto-focus first input
  useEffect(() => {
    if (!isBackupMode) {
      inputRefs.current[0]?.focus()
    }
  }, [isBackupMode])

  const handleCodeChange = (index: number, value: string) => {
    // Only allow digits
    const digit = value.replace(/\D/g, '').slice(-1)

    const newCode = [...code]
    newCode[index] = digit
    setCode(newCode)

    // Auto-advance to next input
    if (digit && index < 5) {
      inputRefs.current[index + 1]?.focus()
    }

    // Auto-submit when all digits entered
    if (digit && index === 5 && newCode.every(d => d)) {
      handleSubmit(newCode.join(''))
    }
  }

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (pasted.length === 6) {
      const newCode = pasted.split('')
      setCode(newCode)
      inputRefs.current[5]?.focus()
      handleSubmit(pasted)
    }
  }

  const handleSubmit = async (codeValue?: string) => {
    const submitCode = codeValue || (isBackupMode ? backupCode : code.join(''))

    if (!submitCode || (!isBackupMode && submitCode.length !== 6)) {
      setError('Please enter a valid code')
      return
    }

    setError('')
    setIsSubmitting(true)

    try {
      const result = await verifyTotp(wallId, sessionId, submitCode, isBackupMode)

      if (result.success) {
        window.location.href = redirectUrl
      } else {
        setError(result.message || 'Invalid verification code')
        if (!isBackupMode) {
          setCode(['', '', '', '', '', ''])
          inputRefs.current[0]?.focus()
        }
      }
    } catch {
      setError('An error occurred. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const loginUrl = `/__auth/login?wall=${wallId}&redirect=${encodeURIComponent(redirectUrl)}`

  return (
    <div className="auth-layout items-center justify-center p-6">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader className="text-center">
            <Link
              to={loginUrl}
              className="inline-flex items-center gap-2 text-sm text-white/50 hover:text-white/70 mb-4 justify-center"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to login
            </Link>

            <div className="mx-auto w-12 h-12 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center mb-4">
              <ShieldCheck className="w-6 h-6 text-cyan-400" />
            </div>

            <CardTitle>Two-Factor Authentication</CardTitle>
            <CardDescription>
              {isBackupMode
                ? 'Enter one of your backup codes'
                : 'Enter the 6-digit code from your authenticator app'}
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-6">
            {error && (
              <div className="alert-error flex items-start gap-3">
                <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
                <p className="text-sm">{error}</p>
              </div>
            )}

            {!isBackupMode ? (
              <>
                {/* 6-digit code input */}
                <div className="flex gap-2 justify-center" onPaste={handlePaste}>
                  {code.map((digit, index) => (
                    <Input
                      key={index}
                      ref={(el) => (inputRefs.current[index] = el)}
                      type="text"
                      inputMode="numeric"
                      maxLength={1}
                      value={digit}
                      onChange={(e) => handleCodeChange(index, e.target.value)}
                      onKeyDown={(e) => handleKeyDown(index, e)}
                      className="w-12 h-14 text-center text-xl font-mono"
                      disabled={isSubmitting}
                    />
                  ))}
                </div>

                <Button
                  className="w-full h-11"
                  onClick={() => handleSubmit()}
                  disabled={isSubmitting || code.some(d => !d)}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Verifying...
                    </>
                  ) : (
                    'Verify Code'
                  )}
                </Button>
              </>
            ) : (
              <>
                {/* Backup code input */}
                <div className="relative">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
                  <Input
                    type="text"
                    placeholder="Enter backup code"
                    className="pl-10 font-mono"
                    value={backupCode}
                    onChange={(e) => setBackupCode(e.target.value.toUpperCase())}
                    disabled={isSubmitting}
                    autoFocus
                  />
                </div>

                <Button
                  className="w-full h-11"
                  onClick={() => handleSubmit()}
                  disabled={isSubmitting || !backupCode}
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Verifying...
                    </>
                  ) : (
                    'Use Backup Code'
                  )}
                </Button>
              </>
            )}

            {/* Toggle backup code mode */}
            <div className="text-center">
              <button
                type="button"
                onClick={() => {
                  setIsBackupMode(!isBackupMode)
                  setError('')
                  setCode(['', '', '', '', '', ''])
                  setBackupCode('')
                }}
                className="text-sm text-cyan-400 hover:text-cyan-300"
              >
                {isBackupMode
                  ? 'Use authenticator app instead'
                  : 'Use a backup code instead'}
              </button>
            </div>

            <p className="text-center text-xs text-white/30">
              Protected by Ghostwire Proxy
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
