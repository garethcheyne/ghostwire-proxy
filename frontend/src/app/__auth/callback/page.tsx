"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Loader2, CheckCircle, XCircle } from "lucide-react";
import Link from "next/link";

export default function CallbackPage() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // The OAuth callback is handled by the backend which sets the cookie
    // and redirects to the original URL. This page is a fallback.

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const errorParam = searchParams.get("error");
    const errorDescription = searchParams.get("error_description");

    if (errorParam) {
      setStatus("error");
      setError(errorDescription || errorParam || "Authentication failed");
      return;
    }

    if (!code || !state) {
      setStatus("error");
      setError("Invalid callback parameters");
      return;
    }

    // If we reach this page, the backend redirect didn't work
    // This could be a configuration issue
    setStatus("error");
    setError("OAuth callback not properly configured. Please contact your administrator.");
  }, [searchParams]);

  return (
    <div className="space-y-6">
      <div className="text-center space-y-4">
        {status === "loading" && (
          <>
            <div className="mx-auto w-16 h-16 rounded-full bg-cyan-500/10 flex items-center justify-center">
              <Loader2 className="h-8 w-8 text-cyan-500 animate-spin" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight">
              Completing sign in...
            </h2>
            <p className="text-muted-foreground text-sm">
              Please wait while we verify your authentication.
            </p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="mx-auto w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center">
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight">
              Sign in successful
            </h2>
            <p className="text-muted-foreground text-sm">
              Redirecting you to your destination...
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <div className="mx-auto w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
              <XCircle className="h-8 w-8 text-red-500" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight">
              Authentication failed
            </h2>
            <Alert variant="destructive" className="mt-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
            <div className="mt-6">
              <Button asChild variant="outline">
                <Link href="/__auth/login">Try again</Link>
              </Button>
            </div>
          </>
        )}
      </div>

      {/* Footer */}
      <p className="text-center text-xs text-muted-foreground mt-8">
        Protected by Ghostwire Proxy Authentication
      </p>
    </div>
  );
}
