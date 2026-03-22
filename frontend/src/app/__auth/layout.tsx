"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

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

export default function AuthPortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const searchParams = useSearchParams();
  const wallId = searchParams.get("wall");
  const [config, setConfig] = useState<AuthWallConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (wallId) {
      fetch(`/api/auth-portal/${wallId}/config`)
        .then((res) => {
          if (!res.ok) throw new Error("Failed to load auth wall configuration");
          return res.json();
        })
        .then(setConfig)
        .catch((err) => setError(err.message));
    }
  }, [wallId]);

  return (
    <div className="min-h-screen flex">
      {/* Scan line & grid animations */}
      <style>{`
        @keyframes scanline {
          0% { transform: translateY(-100%); opacity: 0; }
          10% { opacity: 1; }
          90% { opacity: 1; }
          100% { transform: translateY(100vh); opacity: 0; }
        }
        @keyframes flicker {
          0%, 100% { opacity: 1; }
          92% { opacity: 1; }
          93% { opacity: 0.4; }
          94% { opacity: 1; }
          96% { opacity: 0.6; }
          97% { opacity: 1; }
        }
        @keyframes floatUp {
          0% { transform: translateY(20px); opacity: 0; }
          100% { transform: translateY(0); opacity: 1; }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .scanline {
          animation: scanline 6s linear infinite;
        }
        .flicker {
          animation: flicker 8s ease-in-out infinite;
        }
        .float-up-1 { animation: floatUp 0.6s ease forwards; animation-delay: 0.1s; opacity: 0; }
        .float-up-2 { animation: floatUp 0.6s ease forwards; animation-delay: 0.2s; opacity: 0; }
        .float-up-3 { animation: floatUp 0.6s ease forwards; animation-delay: 0.3s; opacity: 0; }
        .cursor-blink { animation: blink 1s step-end infinite; }
      `}</style>

      {/* Left side - Branding */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-[#050a0f] p-12 flex-col justify-between">
        {/* Dot grid background */}
        <div className="absolute inset-0 bg-[radial-gradient(rgba(0,220,180,0.08)_1px,transparent_1px)] [background-size:28px_28px]" />

        {/* Corner glow accents */}
        <div className="absolute -top-32 -left-32 w-96 h-96 bg-cyan-500/8 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -right-32 w-96 h-96 bg-violet-500/8 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-cyan-500/3 rounded-full blur-3xl pointer-events-none" />

        {/* Animated scan line */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="scanline absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent" />
        </div>

        {/* Top border glow */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-violet-500/30 to-transparent" />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-4 flicker">
          <div className="relative">
            <div className="absolute inset-0 scale-150 bg-cyan-400/20 rounded-full blur-lg animate-pulse" />
            <svg
              className="relative h-10 w-10"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z"
                stroke="currentColor"
                strokeWidth="2"
                className="text-cyan-400"
              />
              <path
                d="M12 16C14.2091 16 16 14.2091 16 12C16 9.79086 14.2091 8 12 8C9.79086 8 8 9.79086 8 12C8 14.2091 9.79086 16 12 16Z"
                fill="currentColor"
                className="text-cyan-400"
              />
            </svg>
          </div>
          <div>
            <span className="text-xl font-bold text-white tracking-widest uppercase">
              {config?.name || "Protected Area"}
            </span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
              <span className="text-[10px] font-mono text-amber-400/80 uppercase tracking-widest">
                Authentication Required
              </span>
            </div>
          </div>
        </div>

        {/* Main content */}
        <div className="relative z-10 space-y-10">
          <div>
            <div className="flex items-center gap-2 mb-5">
              <div className="h-px w-6 bg-cyan-400/60" />
              <span className="text-[10px] font-mono text-cyan-400/70 uppercase tracking-[0.25em]">
                Secure Access
              </span>
            </div>
            <h1 className="text-5xl font-black text-white leading-[1.1] tracking-tight mb-5">
              Sign in to<br />
              <span className="relative">
                <span className="bg-gradient-to-r from-cyan-400 via-teal-300 to-blue-400 bg-clip-text text-transparent">
                  continue
                </span>
              </span>
            </h1>
            <p className="text-sm text-white/35 max-w-sm leading-relaxed font-mono">
              This resource is protected by Ghostwire Proxy authentication.
              Please sign in with your credentials to access.
            </p>
          </div>

          {/* Security info */}
          <div className="font-mono text-sm space-y-0 border border-white/5 rounded-lg overflow-hidden bg-white/[0.02] backdrop-blur-sm">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/5 bg-white/[0.03]">
              <div className="h-2.5 w-2.5 rounded-full bg-green-500/60" />
              <span className="ml-2 text-[10px] text-white/20 tracking-widest">
                Security Status
              </span>
            </div>
            <div className="px-4 py-3 space-y-2.5">
              <div className="float-up-1 flex items-center gap-3">
                <span className="text-green-400">✓</span>
                <span className="text-white/40">Encrypted connection (TLS)</span>
              </div>
              <div className="float-up-2 flex items-center gap-3">
                <span className="text-green-400">✓</span>
                <span className="text-white/40">Server-side session management</span>
              </div>
              <div className="float-up-3 flex items-center gap-3">
                <span className="text-green-400">✓</span>
                <span className="text-white/40">Session expires after {config?.session_timeout || 3600} seconds</span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <p className="relative z-10 text-white/15 text-[10px] font-mono uppercase tracking-[0.3em]">
          Powered by Ghostwire Proxy
        </p>
      </div>

      {/* Right side - Auth form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-background">
        <div className="w-full max-w-md">
          {error ? (
            <div className="text-center">
              <div className="text-red-500 mb-4">{error}</div>
              <p className="text-muted-foreground text-sm">
                Please contact your administrator if this problem persists.
              </p>
            </div>
          ) : (
            children
          )}
        </div>
      </div>
    </div>
  );
}
