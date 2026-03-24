'use client'

import { FileText } from 'lucide-react'
import Link from 'next/link'

const LICENSE_TEXT = `MIT License

Copyright (c) 2024-2026 Gareth Cheyne

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`

const THIRD_PARTY = [
  { name: 'Next.js', license: 'MIT', url: 'https://github.com/vercel/next.js' },
  { name: 'React', license: 'MIT', url: 'https://github.com/facebook/react' },
  { name: 'FastAPI', license: 'MIT', url: 'https://github.com/tiangolo/fastapi' },
  { name: 'OpenResty', license: 'BSD-2-Clause', url: 'https://github.com/openresty/openresty' },
  { name: 'Tailwind CSS', license: 'MIT', url: 'https://github.com/tailwindlabs/tailwindcss' },
  { name: 'shadcn/ui', license: 'MIT', url: 'https://github.com/shadcn-ui/ui' },
  { name: 'Radix UI', license: 'MIT', url: 'https://github.com/radix-ui/primitives' },
  { name: 'Lucide Icons', license: 'ISC', url: 'https://github.com/lucide-icons/lucide' },
  { name: 'SQLAlchemy', license: 'MIT', url: 'https://github.com/sqlalchemy/sqlalchemy' },
  { name: 'Alembic', license: 'MIT', url: 'https://github.com/sqlalchemy/alembic' },
  { name: 'Leaflet', license: 'BSD-2-Clause', url: 'https://github.com/Leaflet/Leaflet' },
  { name: 'Recharts', license: 'MIT', url: 'https://github.com/recharts/recharts' },
  { name: 'PostgreSQL', license: 'PostgreSQL', url: 'https://www.postgresql.org/' },
  { name: 'Redis', license: 'BSD-3-Clause', url: 'https://github.com/redis/redis' },
  { name: 'Docker', license: 'Apache-2.0', url: 'https://www.docker.com/' },
]

export default function LicensePage() {
  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 pt-4">
        <FileText className="h-6 w-6 text-cyan-400" />
        <div>
          <h1 className="text-2xl font-bold">License</h1>
          <p className="text-sm text-muted-foreground">
            Ghostwire Proxy is open source software released under the MIT License
          </p>
        </div>
      </div>

      {/* MIT License */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border p-4 flex items-center justify-between">
          <h2 className="font-semibold">MIT License</h2>
          <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/10 text-green-500 border border-green-500/20">
            Open Source
          </span>
        </div>
        <div className="p-6">
          <pre className="text-sm text-muted-foreground whitespace-pre-wrap font-mono leading-relaxed">
            {LICENSE_TEXT}
          </pre>
        </div>
      </div>

      {/* What this means */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="font-semibold mb-3">What does the MIT License mean?</h2>
        <div className="space-y-3 text-sm text-muted-foreground">
          <div className="flex items-start gap-3">
            <span className="text-green-400 font-bold shrink-0">✓</span>
            <div><strong className="text-foreground">Commercial use</strong> — You can use this software for commercial purposes.</div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-green-400 font-bold shrink-0">✓</span>
            <div><strong className="text-foreground">Modification</strong> — You can modify the source code as you see fit.</div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-green-400 font-bold shrink-0">✓</span>
            <div><strong className="text-foreground">Distribution</strong> — You can distribute the original or modified software.</div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-green-400 font-bold shrink-0">✓</span>
            <div><strong className="text-foreground">Private use</strong> — You can use the software for private purposes.</div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-yellow-400 font-bold shrink-0">!</span>
            <div><strong className="text-foreground">License notice</strong> — You must include the MIT license notice in copies.</div>
          </div>
          <div className="flex items-start gap-3">
            <span className="text-red-400 font-bold shrink-0">✗</span>
            <div><strong className="text-foreground">No warranty</strong> — The software is provided as-is without warranty.</div>
          </div>
        </div>
      </div>

      {/* Third-party */}
      <div className="rounded-xl border border-border bg-card">
        <div className="border-b border-border p-4">
          <h2 className="font-semibold">Third-Party Licenses</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Ghostwire Proxy is built on the shoulders of these open source projects
          </p>
        </div>
        <div className="divide-y divide-border">
          {THIRD_PARTY.map((dep) => (
            <div key={dep.name} className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <a
                  href={dep.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium hover:text-cyan-400 transition-colors"
                >
                  {dep.name}
                </a>
              </div>
              <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground font-mono">
                {dep.license}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Back link */}
      <div className="text-center pb-8">
        <Link
          href="/dashboard/about"
          className="text-sm text-cyan-400 hover:underline"
        >
          ← Back to About
        </Link>
      </div>
    </div>
  )
}
