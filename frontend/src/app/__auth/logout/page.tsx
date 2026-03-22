"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Loader2, LogOut, CheckCircle } from "lucide-react";
import Link from "next/link";

export default function LogoutPage() {
  const searchParams = useSearchParams();
  const wallId = searchParams.get("wall");
  const redirectUrl = searchParams.get("redirect") || "/";

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!wallId) {
      setStatus("error");
      setError("No auth wall specified");
      return;
    }

    // Call logout endpoint
    fetch(`/api/auth-portal/${wallId}/logout`, {
      method: "POST",
      credentials: "include",
    })
      .then((res) => {
        if (!res.ok) throw new Error("Logout failed");
        return res.json();
      })
      .then(() => {
        setStatus("success");
        // Redirect after a short delay
        setTimeout(() => {
          window.location.href = `/__auth/login?wall=${wallId}&redirect=${encodeURIComponent(redirectUrl)}`;
        }, 1500);
      })
      .catch((err) => {
        setStatus("error");
        setError(err.message);
      });
  }, [wallId, redirectUrl]);

  return (
    <div className="space-y-6">
      <div className="text-center space-y-4">
        {status === "loading" && (
          <>
            <div className="mx-auto w-16 h-16 rounded-full bg-cyan-500/10 flex items-center justify-center">
              <Loader2 className="h-8 w-8 text-cyan-500 animate-spin" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight">
              Signing out...
            </h2>
            <p className="text-muted-foreground text-sm">
              Please wait while we end your session.
            </p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="mx-auto w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center">
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight">
              Signed out successfully
            </h2>
            <p className="text-muted-foreground text-sm">
              Redirecting you to the login page...
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <div className="mx-auto w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
              <LogOut className="h-8 w-8 text-red-500" />
            </div>
            <h2 className="text-2xl font-bold tracking-tight">
              Logout failed
            </h2>
            <Alert variant="destructive" className="mt-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
            <div className="mt-6 space-x-4">
              <Button
                variant="outline"
                onClick={() => window.location.reload()}
              >
                Try again
              </Button>
              <Button asChild>
                <Link href={`/__auth/login?wall=${wallId}`}>
                  Go to login
                </Link>
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
