import "server-only";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export type DemoSample = {
  label: "Curious" | "Annoyed" | "Hurt" | "Playful";
  direction: string;
  audio_id: string;
  url: string;
};

const expectedLabels: DemoSample["label"][] = ["Curious", "Annoyed", "Hurt", "Playful"];

export async function loadDemoSamples(): Promise<DemoSample[]> {
  try {
    const manifestText = await readFile(join(process.cwd(), "public", "demo-audio.json"), "utf8");
    const value: unknown = JSON.parse(manifestText);
    if (!Array.isArray(value) || value.length !== expectedLabels.length) return [];

    const apiOrigin = process.env.API_INTERNAL_URL?.replace(/\/$/, "");
    if (!apiOrigin) return [];

    const samples = value.map((item, index) => {
      if (!item || typeof item !== "object") throw new Error("Invalid demo manifest entry.");
      const entry = item as Record<string, unknown>;
      if (entry.label !== expectedLabels[index]
        || typeof entry.direction !== "string"
        || entry.direction.length < 2 || entry.direction.length > 120
        || typeof entry.audio_id !== "string"
        || !/^[a-zA-Z0-9-]{8,64}$/.test(entry.audio_id)) {
        throw new Error("Invalid demo manifest entry.");
      }
      return { label: entry.label as DemoSample["label"], direction: entry.direction, audio_id: entry.audio_id, url: `/api/v1/audio/${encodeURIComponent(entry.audio_id)}` };
    });

    const available = await Promise.all(samples.map(async sample => {
      try {
        const response = await fetch(`${apiOrigin}/api/v1/audio/${encodeURIComponent(sample.audio_id)}`, {
          headers: { Range: "bytes=0-0" },
          cache: "no-store",
          signal: AbortSignal.timeout(5000),
        });
        await response.body?.cancel();
        return response.status === 206 && response.headers.get("content-type")?.startsWith("audio/mpeg");
      } catch {
        return false;
      }
    }));

    return available.every(Boolean) ? samples : [];
  } catch {
    return [];
  }
}
