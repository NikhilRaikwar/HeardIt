import { NextResponse } from "next/server";
import { createAdminSession } from "@/lib/admin-session";

export async function POST(request: Request) {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && fetchSite !== "same-origin") return new NextResponse(null, { status: 403 });
  const key = process.env.ADMIN_KEY;
  if (!key || key.length < 32) return new NextResponse(null, { status: 404 });

  const form = await request.formData();
  const supplied = form.get("key");
  if (typeof supplied !== "string" || supplied.length !== key.length) {
    return NextResponse.redirect(new URL("/admin", request.url), 303);
  }
  const { timingSafeEqual } = await import("node:crypto");
  if (!timingSafeEqual(Buffer.from(supplied), Buffer.from(key))) {
    return NextResponse.redirect(new URL("/admin", request.url), 303);
  }

  const response = NextResponse.redirect(new URL("/admin", request.url), 303);
  response.cookies.set("heardit-admin-session", createAdminSession(key), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/admin",
    maxAge: 60 * 60,
  });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
