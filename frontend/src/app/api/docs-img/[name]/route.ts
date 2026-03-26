import { NextRequest, NextResponse } from 'next/server'
import { resolveDocImage } from '@/lib/docs'
import fs from 'fs'
import path from 'path'

const MIME_TYPES: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name } = await params

  // Sanitize: only allow simple filenames, no path traversal
  if (!name || /[/\\]/.test(name) || name.includes('..')) {
    return new NextResponse('Not found', { status: 404 })
  }

  const filePath = resolveDocImage(name)
  if (!filePath) {
    return new NextResponse('Not found', { status: 404 })
  }

  const ext = path.extname(name).toLowerCase()
  const contentType = MIME_TYPES[ext] || 'application/octet-stream'

  const fileBuffer = fs.readFileSync(filePath)
  return new NextResponse(fileBuffer, {
    headers: {
      'Content-Type': contentType,
      'Cache-Control': 'public, max-age=86400, immutable',
    },
  })
}
