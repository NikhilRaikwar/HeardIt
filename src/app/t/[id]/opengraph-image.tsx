import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "HeardIt listening experiment: the same words can have four meanings.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "72px 84px",
          background: "#fcfbfe",
          color: "#17141d",
          fontFamily: "Arial, sans-serif",
          position: "relative",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 30, fontWeight: 700 }}>
          <div style={{ width: 56, height: 56, borderRadius: 16, background: "#704bef", color: "white", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28 }}>♫</div>
          <span>heard<span style={{ color: "#704bef" }}>it</span></span>
        </div>
        <div style={{ marginTop: 64, fontSize: 76, lineHeight: 1.04, fontWeight: 700, letterSpacing: -4 }}>
          Same words.
        </div>
        <div style={{ fontSize: 76, lineHeight: 1.04, color: "#704bef", fontStyle: "italic", fontFamily: "Georgia, serif", letterSpacing: -3 }}>
          Four meanings.
        </div>
        <div style={{ marginTop: 28, fontSize: 28, color: "#777284" }}>
          A small experiment in what voices communicate.
        </div>
        <div style={{ position: "absolute", right: 86, bottom: 96, display: "flex", alignItems: "center", gap: 10, height: 100, color: "#9878f4" }}>
          {[24, 42, 30, 58, 38, 76, 46, 92, 50, 72, 34, 56, 28, 42, 20].map((height, index) => (
            <div key={index} style={{ width: 8, height, borderRadius: 8, background: "#9878f4" }} />
          ))}
        </div>
      </div>
    ),
    size,
  );
}
