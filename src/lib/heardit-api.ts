import createClient from "openapi-fetch";
import type { components, paths } from "@/lib/api-schema";

const client = createClient<paths>({ baseUrl: "" });

function messageFrom(value: unknown): string | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const nested = record.error;
  if (nested && typeof nested === "object" && "message" in nested && typeof nested.message === "string") {
    return nested.message;
  }
  if (typeof record.detail === "string") return record.detail;
  return undefined;
}

function unwrap<T>(data: T | undefined, error: unknown, response: Response): T {
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new Error(`HeardIt API returned an unexpected response (HTTP ${response.status}). Check that the FastAPI service is running and reachable.`);
  }
  if (!response.ok || error !== undefined) {
    throw new Error(messageFrom(error) || `HeardIt API request failed (HTTP ${response.status}). Try again.`);
  }
  if (data === undefined) {
    throw new Error(`HeardIt API returned an empty response (HTTP ${response.status}).`);
  }
  return data;
}

async function jsonRequest<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  try {
    const result = await request;
    return unwrap(result.data, result.error, result.response);
  } catch (error) {
    if (error instanceof Error && error.message) throw error;
    throw new Error("HeardIt API could not be reached. Check your connection and try again.");
  }
}

export const hearditApi = {
  suggest: (body: components["schemas"]["SuggestRequest"]) =>
    jsonRequest(client.POST("/api/v1/suggestions", { body })),

  generateAudio: (body: components["schemas"]["GenerateRequest"]) =>
    jsonRequest(client.POST("/api/v1/audio/generate", { body })),

  publishTest: (body: components["schemas"]["CreateTest"], idempotencyKey?: string) =>
    jsonRequest(client.POST("/api/v1/tests", {
      body,
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    })),

  creatorTest: (id: string, token: string) =>
    jsonRequest(client.GET("/api/v1/tests/{test_id}/creator", {
      params: { path: { test_id: id } },
      headers: { "x-management-token": token },
    })),

  assignment: (id: string, participantId: string) =>
    jsonRequest(client.POST("/api/v1/tests/{test_id}/assignment", {
      params: { path: { test_id: id } },
      body: { participant_id: participantId },
    })),

  publicTest: (id: string, participantId: string, assignmentToken: string) =>
    jsonRequest(client.GET("/api/v1/tests/{test_id}/public", {
      params: { path: { test_id: id }, query: { participant_id: participantId } },
      headers: { "x-assignment-token": assignmentToken },
    })),

  vote: (id: string, body: components["schemas"]["VoteRequest"]) =>
    jsonRequest(client.POST("/api/v1/tests/{test_id}/votes", {
      params: { path: { test_id: id } },
      body,
    })),

  results: (id: string, token: string) =>
    jsonRequest(client.GET("/api/v1/tests/{test_id}/results", {
      params: { path: { test_id: id } },
      headers: { "x-management-token": token },
    })),
};
