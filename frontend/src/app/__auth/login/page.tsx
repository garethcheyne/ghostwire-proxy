"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { Github, Loader2, Mail, Lock, User } from "lucide-react";

interface AuthWallConfig {
  id: string;
  name: string;
  auth_type: string;
  session_timeout: number;
  providers: Array<{
    id: string;
    name: string;
    provider_type: string;
    enabled: boolean;
  }>;
  has_local_users: boolean;
  has_ldap: boolean;
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const wallId = searchParams.get("wall");
  const redirectUrl = searchParams.get("redirect") || "/";

  const [config, setConfig] = useState<AuthWallConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Local login state
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!wallId) {
      setError("No auth wall specified");
      setLoading(false);
      return;
    }

    fetch(`/api/auth-portal/${wallId}/config`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load configuration");
        return res.json();
      })
      .then((data) => {
        setConfig(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [wallId]);

  const handleLocalLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!wallId) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const res = await fetch(`/api/auth-portal/${wallId}/login/local`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
        credentials: "include",
      });

      const data = await res.json();

      if (!data.success) {
        setError(data.message || "Login failed");
        setIsSubmitting(false);
        return;
      }

      if (data.requires_totp) {
        // Redirect to TOTP verification
        router.push(
          `/__auth/totp?wall=${wallId}&session=${data.partial_session_id}&redirect=${encodeURIComponent(redirectUrl)}`
        );
        return;
      }

      // Login successful - redirect to original URL
      window.location.href = redirectUrl;
    } catch (err) {
      setError("An error occurred. Please try again.");
      setIsSubmitting(false);
    }
  };

  const handleOAuthLogin = (providerId: string) => {
    if (!wallId) return;

    // Redirect to OAuth start endpoint
    window.location.href = `/api/auth-portal/${wallId}/oauth/${providerId}/start?redirect_url=${encodeURIComponent(redirectUrl)}`;
  };

  const getProviderIcon = (providerType: string) => {
    switch (providerType) {
      case "google":
        return (
          <svg className="h-5 w-5" viewBox="0 0 24 24">
            <path
              fill="currentColor"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="currentColor"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="currentColor"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            />
            <path
              fill="currentColor"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            />
          </svg>
        );
      case "github":
        return <Github className="h-5 w-5" />;
      default:
        return <Mail className="h-5 w-5" />;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-500" />
      </div>
    );
  }

  if (!config) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {error || "Unable to load authentication configuration"}
        </AlertDescription>
      </Alert>
    );
  }

  const oauthProviders = config.providers.filter(
    (p) => p.enabled && p.provider_type !== "local"
  );
  const hasOAuth = oauthProviders.length > 0;
  const hasLocal = config.has_local_users;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <h2 className="text-2xl font-bold tracking-tight">Sign in</h2>
        <p className="text-muted-foreground text-sm">
          Access {config.name}
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* OAuth providers */}
      {hasOAuth && (
        <div className="space-y-3">
          {oauthProviders.map((provider) => (
            <Button
              key={provider.id}
              variant="outline"
              className="w-full h-11 gap-3"
              onClick={() => handleOAuthLogin(provider.id)}
            >
              {getProviderIcon(provider.provider_type)}
              Continue with {provider.name}
            </Button>
          ))}
        </div>
      )}

      {/* Separator */}
      {hasOAuth && hasLocal && (
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <Separator className="w-full" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-background px-2 text-muted-foreground">
              Or continue with
            </span>
          </div>
        </div>
      )}

      {/* Local login form */}
      {hasLocal && (
        <form onSubmit={handleLocalLogin} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="username" className="text-sm font-medium">
              Username
            </Label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="username"
                type="text"
                placeholder="Enter your username"
                className="pl-10 h-11"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="password" className="text-sm font-medium">
              Password
            </Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                className="pl-10 h-11"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isSubmitting}
              />
            </div>
          </div>

          <Button
            type="submit"
            className="w-full h-11 bg-cyan-600 hover:bg-cyan-700"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Signing in...
              </>
            ) : (
              "Sign in"
            )}
          </Button>
        </form>
      )}

      {/* No auth methods available */}
      {!hasOAuth && !hasLocal && (
        <Alert>
          <AlertDescription>
            No authentication methods are configured for this resource.
            Please contact your administrator.
          </AlertDescription>
        </Alert>
      )}

      {/* Footer */}
      <p className="text-center text-xs text-muted-foreground">
        Protected by Ghostwire Proxy Authentication
      </p>
    </div>
  );
}
