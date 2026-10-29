"use client"

import * as React from "react"
import { Activity, CheckCircle2, XCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"

import type { AnalyticsSettingsChange, AnalyticsSettingsValue, AnalyticsTestResult } from "./types"

/**
 * The "Ghostwire Analytics" settings card, the same in every app. The app supplies the stored value
 * and two server calls; the ingest key never comes back to the browser (`ingestKeySet` says whether
 * one is stored).
 */
export function AnalyticsSettings({
  value,
  onSave,
  onTest,
}: {
  value: AnalyticsSettingsValue
  onSave: (change: AnalyticsSettingsChange) => Promise<void>
  onTest: (change: AnalyticsSettingsChange) => Promise<AnalyticsTestResult>
}) {
  const [enabled, setEnabled] = React.useState(value.enabled)
  const [url, setUrl] = React.useState(value.url)
  const [websiteId, setWebsiteId] = React.useState(value.websiteId)
  const [traceSample, setTraceSample] = React.useState(String(value.traceSample))
  const [browser, setBrowser] = React.useState(value.browser)
  const [replay, setReplay] = React.useState(value.replay)
  const [ingestKey, setIngestKey] = React.useState("")
  const [removeKey, setRemoveKey] = React.useState(false)
  const [busy, setBusy] = React.useState<"save" | "test" | null>(null)
  const [result, setResult] = React.useState<AnalyticsTestResult | null>(null)

  const sample = Math.min(100, Math.max(0, Number.parseInt(traceSample, 10) || 0))

  const change = (): AnalyticsSettingsChange => ({
    enabled,
    url: url.trim(),
    websiteId: websiteId.trim(),
    traceSample: sample,
    browser,
    replay: browser && replay,
    ...(removeKey ? { ingestKey: "" } : ingestKey.trim() ? { ingestKey: ingestKey.trim() } : {}),
  })

  async function run(kind: "save" | "test") {
    setBusy(kind)
    setResult(null)
    try {
      if (kind === "test") {
        setResult(await onTest(change()))
      } else {
        await onSave(change())
        setIngestKey("")
        setRemoveKey(false)
        setResult({ ok: true, message: "Saved. Changes apply within a minute." })
      }
    } catch (error) {
      setResult({ ok: false, message: error instanceof Error ? error.message : "Something went wrong." })
    } finally {
      setBusy(null)
    }
  }

  const keyStored = value.ingestKeySet && !removeKey

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="size-4 text-primary" />
          Ghostwire Analytics
        </CardTitle>
        <CardDescription>
          Send this stack&apos;s monitoring to a Ghostwire Analytics site: requests and latency per endpoint, traces,
          database and outside calls, jobs and workers, containers, the host and errors. Create the site in Analytics
          first; its settings give the values below.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <Label htmlFor="gw-analytics-enabled">Send monitoring to Ghostwire Analytics</Label>
            <p className="text-sm text-muted-foreground">Nothing is sent while this is off.</p>
          </div>
          <Switch id="gw-analytics-enabled" checked={enabled} onCheckedChange={setEnabled} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="gw-analytics-url">Analytics URL</Label>
          <Input
            id="gw-analytics-url"
            type="url"
            placeholder="https://analytics.example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="gw-analytics-website">Website ID</Label>
          <Input
            id="gw-analytics-website"
            placeholder="From Analytics: Settings → the site → Tracking code"
            value={websiteId}
            onChange={(e) => setWebsiteId(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="gw-analytics-key">Ingest key</Label>
          <div className="flex gap-2">
            <Input
              id="gw-analytics-key"
              type="password"
              autoComplete="off"
              placeholder={keyStored ? "Saved. Type a new key to replace it" : "gwe_… from Analytics: Settings → the site → Errors"}
              value={ingestKey}
              onChange={(e) => {
                setIngestKey(e.target.value)
                setRemoveKey(false)
              }}
            />
            {keyStored && (
              <Button type="button" variant="outline" onClick={() => setRemoveKey(true)}>
                Remove
              </Button>
            )}
          </div>
          <p className="text-sm text-muted-foreground">Required for monitoring. Stored encrypted and never shown again.</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="gw-analytics-sample">Trace sampling (%)</Label>
          <Input
            id="gw-analytics-sample"
            type="number"
            min={0}
            max={100}
            className="w-28"
            value={traceSample}
            onChange={(e) => setTraceSample(e.target.value)}
          />
          <p className="text-sm text-muted-foreground">
            Share of requests recorded as traces. Metrics always count every request.
          </p>
        </div>

        <div className="flex items-center justify-between gap-4">
          <div>
            <Label htmlFor="gw-analytics-browser">Visitor analytics (page views)</Label>
            <p className="text-sm text-muted-foreground">Page views, page speed and front-end errors from the browser.</p>
          </div>
          <Switch id="gw-analytics-browser" checked={browser} onCheckedChange={setBrowser} />
        </div>

        {browser && (
          <div className="flex items-center justify-between gap-4">
            <div>
              <Label htmlFor="gw-analytics-replay">Record sessions (replay and heatmaps)</Label>
              <p className="text-sm text-muted-foreground">
                Records real sessions, with inputs masked. Also needs recording switched on for the site in Analytics.
              </p>
            </div>
            <Switch id="gw-analytics-replay" checked={replay} onCheckedChange={setReplay} />
          </div>
        )}

        {result && (
          <p
            role="status"
            className={`flex items-start gap-2 text-sm ${result.ok ? "text-muted-foreground" : "text-destructive"}`}
          >
            {result.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <XCircle className="mt-0.5 size-4 shrink-0" />}
            {result.message}
          </p>
        )}
      </CardContent>
      <CardFooter className="justify-end gap-2">
        <Button type="button" variant="outline" disabled={busy !== null || !url.trim()} onClick={() => run("test")}>
          {busy === "test" ? "Testing…" : "Test connection"}
        </Button>
        <Button type="button" disabled={busy !== null} onClick={() => run("save")}>
          {busy === "save" ? "Saving…" : "Save"}
        </Button>
      </CardFooter>
    </Card>
  )
}
