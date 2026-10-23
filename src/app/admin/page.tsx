import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { isValidAdminSession } from "@/lib/admin-session";
import type { components } from "@/lib/api-schema";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Private product metrics", robots: { index: false, follow: false } };

type AdminStats = components["schemas"]["AdminStatsResponse"];

const funnelSteps = [
  ["create_started", "Create started"],
  ["voice_generation_completed", "Voice generation completed"],
  ["test_published", "Test published"],
  ["share_clicked", "Share clicked"],
  ["test_opened", "Test opened"],
  ["vote_submitted", "Vote submitted"],
] as const;

async function loadStats(key: string): Promise<AdminStats | null> {
  const apiOrigin = process.env.API_INTERNAL_URL?.replace(/\/$/, "");
  if (!apiOrigin) return null;
  try {
    const response = await fetch(`${apiOrigin}/api/v1/admin/stats`, {
      headers: { "X-Admin-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return null;
    const value: unknown = await response.json();
    if (!value || typeof value !== "object") return null;
    const stats = value as AdminStats;
    return Number.isInteger(stats.server_confirmed?.tests_published)
      && Number.isInteger(stats.server_confirmed?.tests_with_responses)
      && Number.isInteger(stats.server_confirmed?.votes_accepted)
      && stats.client_reported?.funnel
      ? stats
      : null;
  } catch {
    return null;
  }
}

export default async function AdminPage() {
  const key = process.env.ADMIN_KEY;
  if (!key) notFound();
  const session = (await cookies()).get("heardit-admin-session")?.value;
  if (!isValidAdminSession(key, session)) {
    return <main className="hi-admin"><section className="hi-admin-card"><span className="hi-small-label">PRIVATE OPERATIONS</span><h1>HeardIt metrics</h1><p>Enter the configured admin key to view database-backed product counts.</p><form action="/admin/session" method="post"><label htmlFor="admin-key">Admin key</label><input id="admin-key" name="key" type="password" autoComplete="current-password" required/><button className="hi-button" type="submit">Open metrics</button></form></section></main>;
  }

  const stats = await loadStats(key);
  return <main className="hi-admin"><section className="hi-admin-card"><span className="hi-small-label">PRIVATE OPERATIONS</span><h1>HeardIt metrics</h1><p>MongoDB collections confirm published tests and accepted votes. Browser funnel events are client-reported and may be incomplete or spoofed.</p>{stats ? <><h2>Server-confirmed</h2><p>Counts derived from published test and saved vote records.</p><div className="hi-admin-metrics"><article><span>Published tests</span><b>{stats.server_confirmed.tests_published}</b></article><article><span>Tests with responses</span><b>{stats.server_confirmed.tests_with_responses}</b></article><article><span>Accepted votes</span><b>{stats.server_confirmed.votes_accepted}</b></article></div><h2>Client-reported funnel</h2><p>Events sent by browsers. Use as directional product telemetry, not verified outcomes. Events are retained for up to 180 days.</p><ol className="hi-admin-funnel">{funnelSteps.map(([event, label]) => <li key={event}><span>{label}</span><b>{stats.client_reported.funnel[event] ?? 0}</b></li>)}</ol></> : <p role="status">Metrics are unavailable. Check the API connection and matching ADMIN_KEY values on both services.</p>}</section></main>;
}
