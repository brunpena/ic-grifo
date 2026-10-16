import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

export const alt = "IC Grifo: validação de regras em documentos";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const fontsDir = join(process.cwd(), "node_modules/geist/dist/fonts/geist-sans");

export default async function OpengraphImage() {
  const [logo, bold, regular] = await Promise.all([
    readFile(join(process.cwd(), "src/assets/og-logo.png")),
    readFile(join(fontsDir, "Geist-Bold.ttf")),
    readFile(join(fontsDir, "Geist-Regular.ttf")),
  ]);

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          gap: 56,
          padding: "0 96px",
          background: "radial-gradient(circle 360px at 236px 315px, rgba(10,132,255,0.15), #030a1f)",
          backgroundColor: "#030a1f",
          fontFamily: "Geist",
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- ImageResponse só aceita <img> */}
        <img src={`data:image/png;base64,${logo.toString("base64")}`} width={280} height={280} alt="" />
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div
            style={{
              fontSize: 96,
              fontWeight: 700,
              backgroundImage: "linear-gradient(135deg, #22d3ee 0%, #0a84ff 45%, #0038d6 100%)",
              backgroundClip: "text",
              color: "transparent",
            }}
          >
            IC Grifo
          </div>
          <div style={{ fontSize: 34, color: "#a3b1cc", maxWidth: 620, lineHeight: 1.35 }}>
            Encontre e valide as regras de contratos, editais e regulamentos.
          </div>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: "Geist", data: bold, weight: 700, style: "normal" },
        { name: "Geist", data: regular, weight: 400, style: "normal" },
      ],
    },
  );
}
