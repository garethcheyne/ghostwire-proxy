"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ArrowLeft, Loader2, KeyRound, ShieldCheck } from "lucide-react";
import Link from "next/link";

export default function TotpPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const wallId = searchParams.get("wall");
  const sessionId = searchParams.get("session");
  const redirectUrl = searchParams.get("redirect") || "/";

  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showBackupCode, setShowBackupCode] = useState(false);
  const [backupCode, setBackupCode] = useState("");

  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    // Focus first input on mount
    inputRefs.current[0]?.focus();
  }, []);

  const handleCodeChange = (index: number, value: string) => {
    // Only allow digits
    const digit = value.replace(/\D/g, "").slice(-1);

    const newCode = [...code];
    newCode[index] = digit;
    setCode(newCode);

    // Auto-advance to next input
    if (digit && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }

    // Auto-submit when all digits entered
    if (digit && index === 5) {
      const fullCode = newCode.join("");
      if (fullCode.length === 6) {
        handleSubmit(fullCode);
      }
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    // Handle backspace
    if (e.key === "Backspace" && !code[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);

    if (pastedData.length === 6) {
      const newCode = pastedData.split("");
      setCode(newCode);
      handleSubmit(pastedData);
    }
  };

  const handleSubmit = async (codeValue?: string) => {
    const submitCode = codeValue || (showBackupCode ? backupCode : code.join(""));

    if (!wallId || !sessionId) {
      setError("Invalid session. Please start over.");
      return;
    }

    if (showBackupCode && backupCode.length !== 8) {
      setError("Backup code must be 8 characters");
      return;
    }

    if (!showBackupCode && submitCode.length !== 6) {
      setError("Please enter all 6 digits");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const res = await fetch(`/api/auth-portal/${wallId}/login/totp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          partial_session_id: sessionId,
          code: submitCode,
        }),
        credentials: "include",
      });

      const data = await res.json();

      if (!data.success) {
        setError(data.message || "Invalid code");
        setIsSubmitting(false);
        // Clear code on error
        setCode(["", "", "", "", "", ""]);
        setBackupCode("");
        inputRefs.current[0]?.focus();
        return;
      }

      // Success - redirect to original URL
      window.location.href = redirectUrl;
    } catch (err) {
      setError("An error occurred. Please try again.");
      setIsSubmitting(false);
    }
  };

  const handleBackupSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSubmit();
  };

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        href={`/__auth/login?wall=${wallId}&redirect=${encodeURIComponent(redirectUrl)}`}
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to login
      </Link>

      {/* Header */}
      <div className="text-center space-y-2">
        <div className="mx-auto w-12 h-12 rounded-full bg-cyan-500/10 flex items-center justify-center mb-4">
          <ShieldCheck className="h-6 w-6 text-cyan-500" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight">
          Two-Factor Authentication
        </h2>
        <p className="text-muted-foreground text-sm">
          Enter the 6-digit code from your authenticator app
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!showBackupCode ? (
        <>
          {/* TOTP Code Input */}
          <div className="space-y-4">
            <div
              className="flex gap-2 justify-center"
              onPaste={handlePaste}
            >
              {code.map((digit, index) => (
                <Input
                  key={index}
                  ref={(el) => {
                    inputRefs.current[index] = el;
                  }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleCodeChange(index, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(index, e)}
                  className="w-12 h-14 text-center text-2xl font-mono"
                  disabled={isSubmitting}
                />
              ))}
            </div>

            <Button
              type="button"
              className="w-full h-11 bg-cyan-600 hover:bg-cyan-700"
              disabled={isSubmitting || code.join("").length !== 6}
              onClick={() => handleSubmit()}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifying...
                </>
              ) : (
                "Verify"
              )}
            </Button>
          </div>

          {/* Backup code option */}
          <div className="text-center">
            <button
              type="button"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setShowBackupCode(true)}
            >
              Use a backup code instead
            </button>
          </div>
        </>
      ) : (
        <>
          {/* Backup Code Input */}
          <form onSubmit={handleBackupSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="backupCode" className="text-sm font-medium">
                Backup Code
              </Label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="backupCode"
                  type="text"
                  placeholder="Enter 8-character backup code"
                  className="pl-10 h-11 font-mono uppercase tracking-widest"
                  value={backupCode}
                  onChange={(e) => setBackupCode(e.target.value.toUpperCase())}
                  maxLength={8}
                  required
                  disabled={isSubmitting}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Each backup code can only be used once.
              </p>
            </div>

            <Button
              type="submit"
              className="w-full h-11 bg-cyan-600 hover:bg-cyan-700"
              disabled={isSubmitting || backupCode.length !== 8}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Verifying...
                </>
              ) : (
                "Verify Backup Code"
              )}
            </Button>
          </form>

          {/* Back to TOTP option */}
          <div className="text-center">
            <button
              type="button"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => {
                setShowBackupCode(false);
                setBackupCode("");
              }}
            >
              Use authenticator app instead
            </button>
          </div>
        </>
      )}

      {/* Footer */}
      <p className="text-center text-xs text-muted-foreground">
        Protected by Ghostwire Proxy Authentication
      </p>
    </div>
  );
}
