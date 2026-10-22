import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  const heights = [8, 14, 18, 11, 6];
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#704bef",
          borderRadius: "7px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "2px",
            height: "18px",
          }}
        >
          {heights.map((h, i) => (
            <div
              key={i}
              style={{
                width: "2.5px",
                height: `${h}px`,
                background: "#ffffff",
                borderRadius: "2px",
              }}
            />
          ))}
        </div>
      </div>
    ),
    { ...size }
  );
}
