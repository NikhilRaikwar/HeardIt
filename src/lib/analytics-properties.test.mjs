import test from "node:test";
import assert from "node:assert/strict";
import { sanitizeAnalyticsProperties } from "./analytics-properties.mjs";

test("analytics properties discard sentence, direction, identity and capability data", () => {
  const safe = sanitizeAnalyticsProperties({
    surface: "studio",
    cached: true,
    sentence: "private test sentence",
    direction: "[private voice direction]",
    management_token: "creator-secret",
    assignment_token: "assignment-secret",
    participant_id: "browser-id",
    selected_label: "private answer",
  });

  assert.deepEqual(safe, { surface: "studio", cached: true });
  assert.doesNotMatch(JSON.stringify(safe), /private|secret|browser-id/);
});
