#!/usr/bin/env node
// Render PWA icons + OG image from public/brand/pycil-mark.svg.
// Usage: pnpm pwa:render
//
// Outputs:
//   public/icon-192.png            (192x192, transparent)
//   public/icon-512.png            (512x512, transparent)
//   public/icon-maskable.png       (1024x1024, full-bleed safe zone)
//   public/og-image.png            (1200x630, brand bg)

import sharp from "sharp";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC = resolve(__dirname, "..", "public");
const SVG_PATH = resolve(PUBLIC, "brand", "pycil-mark.svg");
const svg = readFileSync(SVG_PATH);

async function renderSquare(size, out) {
  await sharp(svg).resize(size, size).png().toFile(resolve(PUBLIC, out));
  console.log(`wrote ${out}`);
}

async function renderMaskable() {
  // Maskable: 80% safe zone — pad 10% all sides on a brand-color bg.
  const inner = await sharp(svg).resize(820, 820).png().toBuffer();
  await sharp({
    create: { width: 1024, height: 1024, channels: 4, background: "#0F172A" },
  })
    .composite([{ input: inner, top: 102, left: 102 }])
    .png()
    .toFile(resolve(PUBLIC, "icon-maskable.png"));
  console.log("wrote icon-maskable.png");
}

async function renderOg() {
  const inner = await sharp(svg).resize(420, 420).png().toBuffer();
  await sharp({
    create: { width: 1200, height: 630, channels: 4, background: "#0F172A" },
  })
    .composite([{ input: inner, top: 105, left: 80 }])
    .png()
    .toFile(resolve(PUBLIC, "og-image.png"));
  console.log("wrote og-image.png");
}

await renderSquare(192, "icon-192.png");
await renderSquare(512, "icon-512.png");
await renderMaskable();
await renderOg();
