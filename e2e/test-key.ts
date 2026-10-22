import { createHash } from "node:crypto";

// Deterministic local-only fixture. The source phrase is not a credential.
export const e2eAdminKey = createHash("sha256")
  .update("HeardIt Playwright local admin fixture only")
  .digest("hex");
