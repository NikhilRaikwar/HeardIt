const surfaces = new Set(["landing", "hero", "navigation", "footer", "create", "studio", "creator_journey", "creator_preview", "interpretations", "direction", "created_page", "listener", "results", "demo", "demo_setup", "landing_demo", "hero_sample"]);
const emotions = new Set(["curious", "annoyed", "hurt", "playful"]);
const channels = new Set(["x", "linkedin", "whatsapp", "reddit", "native", "link"]);

export function sanitizeAnalyticsProperties(input = {}) {
  const safe = {};
  if (typeof input.surface === "string" && surfaces.has(input.surface)) safe.surface = input.surface;
  if (typeof input.emotion === "string" && emotions.has(input.emotion.toLowerCase())) safe.emotion = input.emotion.toLowerCase();
  if (typeof input.channel === "string" && channels.has(input.channel.toLowerCase())) safe.channel = input.channel.toLowerCase();
  if (input.condition === "audio" || input.condition === "text") safe.condition = input.condition;
  if (typeof input.cached === "boolean") safe.cached = input.cached;
  if (input.model === "s2.1-pro-free") safe.model = input.model;
  return safe;
}
