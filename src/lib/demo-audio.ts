import "server-only";
import { open, readFile } from "node:fs/promises";
import { join } from "node:path";

export type DemoSample = {
  id: string;
  label: "Curious" | "Annoyed" | "Hurt" | "Playful";
  text: string;
  model: "s2.1-pro-free";
  generated_at: string;
  url: string;
};

export const DEMO_SENTENCE = "I thought you said you'd be here by now.";
export const DEMO_LABELS: DemoSample["label"][] = ["Curious", "Annoyed", "Hurt", "Playful"];

export function parseDemoManifest(value: unknown): Omit<DemoSample, "url">[] {
  if (!Array.isArray(value) || value.length !== DEMO_LABELS.length) return [];
  try {
    return value.map((item, index) => {
      if (!item || typeof item !== "object") throw new Error("Invalid demo manifest entry.");
      const entry = item as Record<string, unknown>;
      const label = DEMO_LABELS[index];
      if (entry.id !== label.toLowerCase()
        || entry.label !== label
        || entry.text !== DEMO_SENTENCE
        || entry.model !== "s2.1-pro-free"
        || typeof entry.generated_at !== "string"
        || !Number.isFinite(Date.parse(entry.generated_at))) {
        throw new Error("Invalid demo manifest entry.");
      }
      return {
        id: entry.id,
        label,
        text: entry.text,
        model: "s2.1-pro-free",
        generated_at: entry.generated_at,
      };
    });
  } catch {
    return [];
  }
}

async function isPlayableMpeg(path: string): Promise<boolean> {
  let file;
  try {
    file = await open(path, "r");
    const info = await file.stat();
    if (info.size < 100 || info.size > 4 * 1024 * 1024) return false;
    const head = Buffer.alloc(3);
    const { bytesRead } = await file.read(head, 0, 3, 0);
    return bytesRead >= 2 && (head.toString("ascii", 0, 3) === "ID3" || (head[0] === 255 && (head[1] & 224) === 224));
  } catch {
    return false;
  } finally {
    await file?.close();
  }
}

export async function loadDemoSamples(): Promise<DemoSample[]> {
  const demoDirectory = join(process.cwd(), "public", "demo");
  try {
    const value: unknown = JSON.parse(await readFile(join(demoDirectory, "manifest.json"), "utf8"));
    const manifest = parseDemoManifest(value);
    if (manifest.length !== DEMO_LABELS.length) return [];
    const filesAreReady = await Promise.all(manifest.map(sample => isPlayableMpeg(join(demoDirectory, `${sample.id}.mp3`))));
    if (!filesAreReady.every(Boolean)) return [];
    return manifest.map(sample => ({ ...sample, url: `/demo/${sample.id}.mp3` }));
  } catch {
    return [];
  }
}
