"use client";

import posthog from "posthog-js";
import { sanitizeAnalyticsProperties } from "./analytics-properties.mjs";

let initialized = false;

function configuredPostHog() {
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (typeof window === "undefined" || !key) return null;
  if (!initialized) {
    posthog.init(key, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com",
      autocapture: false,
      capture_pageview: false,
      capture_pageleave: false,
      disable_session_recording: true,
      persistence: "localStorage",
      person_profiles: "identified_only",
    });
    initialized = true;
  }
  return posthog;
}

export function trackProductEvent(event: string, properties: Record<string, unknown> = {}) {
  const safeProperties = sanitizeAnalyticsProperties(properties);
  const analyticsEvent = { event, properties: safeProperties };

  if (typeof window !== "undefined") {
    void fetch("/api/v1/events", {
      method: "POST",
      keepalive: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(analyticsEvent),
    }).catch(() => undefined);
  }

  configuredPostHog()?.capture(event, safeProperties);
}
