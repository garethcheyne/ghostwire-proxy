export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
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
        .float-up-4 { animation: floatUp 0.6s ease forwards; animation-delay: 0.4s; opacity: 0; }
        .float-up-5 { animation: floatUp 0.6s ease forwards; animation-delay: 0.5s; opacity: 0; }
        .float-up-6 { animation: floatUp 0.6s ease forwards; animation-delay: 0.6s; opacity: 0; }
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
            <img
              src="/logo.png"
              alt="Ghostwire Logo"
              className="relative h-10 w-10 object-contain brightness-0 invert"
            />
          </div>
          <div>
            <span className="text-xl font-bold text-white tracking-widest uppercase">Ghostwire</span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-[10px] font-mono text-green-400/80 uppercase tracking-widest">Proxy Online</span>
            </div>
          </div>
        </div>

        {/* Main content */}
        <div className="relative z-10 space-y-10">

          {/* Headline */}
          <div>
            <div className="flex items-center gap-2 mb-5">
              <div className="h-px w-6 bg-cyan-400/60" />
              <span className="text-[10px] font-mono text-cyan-400/70 uppercase tracking-[0.25em]">Reverse Proxy Manager</span>
            </div>
            <h1 className="text-5xl font-black text-white leading-[1.1] tracking-tight mb-5">
              Secure your<br />
              <span className="relative">
                <span className="bg-gradient-to-r from-cyan-400 via-teal-300 to-blue-400 bg-clip-text text-transparent">services</span>
              </span>
              <br />
              <span className="text-3xl font-light text-white/50">with confidence.</span>
            </h1>
            <p className="text-sm text-white/35 max-w-sm leading-relaxed font-mono">
              SSL termination. Auth walls. Traffic monitoring. Complete reverse proxy management.
            </p>
          </div>

          {/* Terminal-style feature list */}
          <div className="font-mono text-sm space-y-0 border border-white/5 rounded-lg overflow-hidden bg-white/[0.02] backdrop-blur-sm">
            {/* Terminal header bar */}
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/5 bg-white/[0.03]">
              <div className="h-2.5 w-2.5 rounded-full bg-red-500/60" />
              <div className="h-2.5 w-2.5 rounded-full bg-yellow-500/60" />
              <div className="h-2.5 w-2.5 rounded-full bg-green-500/60" />
              <span className="ml-2 text-[10px] text-white/20 tracking-widest">ghostwire-proxy — services</span>
            </div>

            <div className="px-4 py-3 space-y-2.5">
              <div className="float-up-1 flex items-center gap-3">
                <span className="text-white/20 select-none">$</span>
                <span className="text-cyan-400/60">status</span>
                <span className="text-white/40 flex-1">nginx-proxy</span>
                <span className="flex items-center gap-1.5 text-green-400 text-xs">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
                  RUNNING
                </span>
              </div>
              <div className="float-up-2 flex items-center gap-3">
                <span className="text-white/20 select-none">$</span>
                <span className="text-cyan-400/60">status</span>
                <span className="text-white/40 flex-1">ssl-manager</span>
                <span className="flex items-center gap-1.5 text-green-400 text-xs">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
                  RUNNING
                </span>
              </div>
              <div className="float-up-3 flex items-center gap-3">
                <span className="text-white/20 select-none">$</span>
                <span className="text-cyan-400/60">status</span>
                <span className="text-white/40 flex-1">auth-wall</span>
                <span className="flex items-center gap-1.5 text-green-400 text-xs">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
                  RUNNING
                </span>
              </div>
              <div className="float-up-4 flex items-center gap-3">
                <span className="text-white/20 select-none">$</span>
                <span className="text-cyan-400/60">status</span>
                <span className="text-white/40 flex-1">traffic-logger</span>
                <span className="flex items-center gap-1.5 text-green-400 text-xs">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
                  RUNNING
                </span>
              </div>
              <div className="float-up-5 flex items-center gap-3">
                <span className="text-white/20 select-none">$</span>
                <span className="text-cyan-400/60">status</span>
                <span className="text-white/40 flex-1">dns-provider</span>
                <span className="flex items-center gap-1.5 text-yellow-400 text-xs">
                  <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse" />
                  STANDBY
                </span>
              </div>
              <div className="float-up-6 flex items-center gap-3">
                <span className="text-white/20 select-none">$</span>
                <span className="text-cyan-400/60">status</span>
                <span className="text-white/40 flex-1">certbot</span>
                <span className="flex items-center gap-1.5 text-green-400 text-xs">
                  <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
                  RUNNING
                </span>
              </div>
              <div className="flex items-center gap-2 pt-1 text-white/20 text-xs">
                <span>▸</span>
                <span className="cursor-blink">_</span>
              </div>
            </div>
          </div>

          {/* Stats strip */}
          <div className="grid grid-cols-3 gap-0 border border-white/5 rounded-lg overflow-hidden">
            <div className="px-5 py-4 bg-white/[0.02] border-r border-white/5 text-center">
              <div className="text-2xl font-black text-cyan-400 font-mono tracking-tight">99.9%</div>
              <div className="text-[10px] text-white/25 mt-1 uppercase tracking-widest font-mono">Uptime</div>
            </div>
            <div className="px-5 py-4 bg-white/[0.02] border-r border-white/5 text-center">
              <div className="text-2xl font-black text-violet-400 font-mono tracking-tight">SSL</div>
              <div className="text-[10px] text-white/25 mt-1 uppercase tracking-widest font-mono">Auto-Renew</div>
            </div>
            <div className="px-5 py-4 bg-white/[0.02] text-center">
              <div className="text-2xl font-black text-green-400 font-mono tracking-tight">&lt;1ms</div>
              <div className="text-[10px] text-white/25 mt-1 uppercase tracking-widest font-mono">Latency</div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <p className="relative z-10 text-white/15 text-[10px] font-mono uppercase tracking-[0.3em]">
          {"// Route. Protect. Monitor."}
        </p>
      </div>

      {/* Right side - Auth form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-background">
        <div className="w-full max-w-md">
          {children}
        </div>
      </div>
    </div>
  )
}
