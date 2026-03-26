import fs from 'fs'
import path from 'path'
import matter from 'gray-matter'
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import remarkRehype from 'remark-rehype'
import rehypeRaw from 'rehype-raw'
import rehypeStringify from 'rehype-stringify'

// Resolve docs directory — works in dev (cwd=frontend) and Docker (volume mount at /app/docs)
function getDocsRoot(): string {
  const candidates = [
    path.join(process.cwd(), 'docs', 'ghostwire-proxy'),
    path.join(process.cwd(), '..', 'docs', 'ghostwire-proxy'),
  ]
  for (const dir of candidates) {
    if (fs.existsSync(dir)) return dir
  }
  return candidates[0]
}

export interface DocMeta {
  title: string
  icon?: string
  description?: string
}

export interface DocPage {
  slug: string[]
  title: string
  excerpt?: string
  content: string
  html: string
  frontmatter: Record<string, unknown>
}

export interface NavItem {
  slug: string
  title: string
  icon?: string
  description?: string
  children?: NavItem[]
  hasIndex?: boolean
}

/**
 * Load _meta.json from a directory, returning an ordered map of key -> metadata
 */
function loadMeta(dir: string): Record<string, DocMeta> {
  const metaPath = path.join(dir, '_meta.json')
  if (!fs.existsSync(metaPath)) return {}
  try {
    const raw = fs.readFileSync(metaPath, 'utf-8')
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

/**
 * Build the navigation tree from the docs directory
 */
export function getNavigation(): NavItem[] {
  const root = getDocsRoot()
  if (!fs.existsSync(root)) return []

  const meta = loadMeta(root)
  const items: NavItem[] = []

  for (const [key, info] of Object.entries(meta)) {
    const childDir = path.join(root, key)
    if (fs.existsSync(childDir) && fs.statSync(childDir).isDirectory()) {
      const childMeta = loadMeta(childDir)
      const children: NavItem[] = []

      for (const [childKey, childInfo] of Object.entries(childMeta)) {
        children.push({
          slug: childKey,
          title: childInfo.title,
          icon: childInfo.icon,
        })
      }

      items.push({
        slug: key,
        title: info.title,
        icon: info.icon,
        description: info.description,
        children,
        hasIndex: fs.existsSync(path.join(childDir, 'index.md')),
      })
    }
  }

  return items
}

/**
 * Pre-process custom markdown syntax before rendering:
 * - :::steps / ::: container directives → ordered list with step styling
 * - [!TIP], [!NOTE], [!WARNING], [!IMPORTANT], [!CAUTION] callouts
 */
function preprocessMarkdown(markdown: string): string {
  // Normalize line endings to LF
  const normalized = markdown.replace(/\r\n/g, '\n')

  // Convert :badge[Text]{variant} to styled spans
  const withBadges = normalized.replace(
    /:badge\[([^\]]+)\]\{(\w+)\}/g,
    (_m, text: string, variant: string) => {
      return `<span class="docs-badge docs-badge-${variant}">${text}</span>`
    }
  )

  // Convert :::steps blocks to ordered lists
  // Steps contain ### headings followed by content
  const processed = withBadges.replace(
    /:::steps\n([\s\S]*?):::/g,
    (_match, body: string) => {
      // Split by ### headings
      const steps: { title: string; body: string }[] = []
      const lines = body.split('\n')
      let currentTitle = ''
      let currentBody: string[] = []

      for (const line of lines) {
        const headingMatch = line.match(/^###\s+(.+)/)
        if (headingMatch) {
          if (currentTitle) {
            steps.push({ title: currentTitle, body: currentBody.join('\n').trim() })
          }
          currentTitle = headingMatch[1]
          currentBody = []
        } else {
          currentBody.push(line)
        }
      }
      if (currentTitle) {
        steps.push({ title: currentTitle, body: currentBody.join('\n').trim() })
      }

      if (steps.length === 0) return body

      // Render as a styled step list
      const stepsHtml = steps.map((step, i) => {
        const num = i + 1
        return `<div class="docs-step">\n<div class="docs-step-number">${num}</div>\n<div class="docs-step-content">\n\n### ${step.title}\n\n${step.body}\n\n</div>\n</div>`
      }).join('\n\n')

      return `<div class="docs-steps">\n\n${stepsHtml}\n\n</div>`
    }
  )

  return processed
}

/**
 * Generate a URL-safe slug from heading text
 */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, '')      // strip HTML tags
    .replace(/&[^;]+;/g, '')      // strip HTML entities
    .replace(/[^a-z0-9\s-]/g, '') // remove non-alphanumeric
    .trim()
    .replace(/\s+/g, '-')         // spaces to hyphens
    .replace(/-+/g, '-')          // collapse hyphens
}

/**
 * Post-process rendered HTML:
 * - Add anchor IDs to headings
 * - Convert GitHub-style [!TYPE] callouts in blockquotes to styled divs
 */
function postprocessHtml(html: string): string {
  const calloutTypes: Record<string, { color: string; icon: string; label: string }> = {
    NOTE: { color: 'blue', icon: 'ℹ️', label: 'Note' },
    TIP: { color: 'green', icon: '💡', label: 'Tip' },
    IMPORTANT: { color: 'purple', icon: '❗', label: 'Important' },
    WARNING: { color: 'amber', icon: '⚠️', label: 'Warning' },
    CAUTION: { color: 'red', icon: '🔴', label: 'Caution' },
  }

  // Add anchor IDs and link icons to headings
  const withAnchors = html.replace(
    /<(h[2-4])>(.*?)<\/\1>/g,
    (_match, tag: string, content: string) => {
      const id = slugify(content)
      return `<${tag} id="${id}"><a href="#${id}" class="docs-heading-anchor">${content}</a></${tag}>`
    }
  )

  // Match blockquotes containing [!TYPE] alerts
  const result = withAnchors.replace(
    /<blockquote>\s*<p>\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*\n?([\s\S]*?)<\/blockquote>/g,
    (_match, type: string, rest: string) => {
      const info = calloutTypes[type] || calloutTypes.NOTE
      // Clean up: the rest might start with </p> and continue with more <p> tags
      let content = rest.trim()
      // Remove trailing </p> if the alert text is on the same line
      if (content.startsWith('\n')) {
        content = content.substring(1)
      }
      return `<div class="docs-callout docs-callout-${info.color}"><div class="docs-callout-title">${info.icon} ${info.label}</div><div class="docs-callout-content">${content}</div></div>`
    }
  )

  return result
}

/**
 * Convert markdown to HTML server-side
 */
function renderMarkdown(markdown: string): string {
  const preprocessed = preprocessMarkdown(markdown)
  const result = unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeStringify)
    .processSync(preprocessed)
  return postprocessHtml(String(result))
}

/**
 * Load a documentation page by slug segments
 */
export function getDocPage(slug: string[]): DocPage | null {
  const root = getDocsRoot()

  // Build candidate file paths
  const candidates: string[] = []

  if (slug.length === 0) {
    candidates.push(path.join(root, 'index.md'))
  } else {
    // Try as a file first, then as directory with index.md
    const joined = slug.join(path.sep)
    candidates.push(path.join(root, `${joined}.md`))
    candidates.push(path.join(root, joined, 'index.md'))
  }

  for (const filePath of candidates) {
    if (fs.existsSync(filePath)) {
      const raw = fs.readFileSync(filePath, 'utf-8')
      const { data, content } = matter(raw)
      // Rewrite image paths before rendering
      // Matches: ./_img/foo.png, _img/foo.png, ../_img/foo.png
      const rewrittenContent = content.replace(
        /!\[([^\]]*)\]\((?:\.\.?\/)?\/?_img\/([^)]+)\)/g,
        '![$1](/api/docs-img/$2)'
      )
      return {
        slug,
        title: (data.title as string) || slug[slug.length - 1] || 'Documentation',
        excerpt: data.excerpt as string | undefined,
        content,
        html: renderMarkdown(rewrittenContent),
        frontmatter: data,
      }
    }
  }

  return null
}

/**
 * Get all doc page slugs for static generation
 */
export function getAllDocSlugs(): string[][] {
  const root = getDocsRoot()
  if (!fs.existsSync(root)) return []

  const slugs: string[][] = []
  slugs.push([]) // root index

  function walk(dir: string, prefix: string[]) {
    const meta = loadMeta(dir)
    for (const key of Object.keys(meta)) {
      const childDir = path.join(dir, key)
      const childFile = path.join(dir, `${key}.md`)

      if (fs.existsSync(childDir) && fs.statSync(childDir).isDirectory()) {
        slugs.push([...prefix, key])
        walk(childDir, [...prefix, key])
      } else if (fs.existsSync(childFile)) {
        slugs.push([...prefix, key])
      }
    }
  }

  walk(root, [])
  return slugs
}

/**
 * Resolve a doc image path to the absolute filesystem path
 */
export function resolveDocImage(imagePath: string): string | null {
  const root = getDocsRoot()
  // Normalize: images reference ../_img/name.png or ./_img/name.png
  // All images are in the root _img/ directory
  const name = path.basename(imagePath)
  const imgPath = path.join(root, '_img', name)
  if (fs.existsSync(imgPath)) return imgPath
  return null
}
