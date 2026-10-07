// Expand the authored canvas to the widget ratio. Shapes retain uniform scaling:
// no cover crop, no contain letterbox, no independent x/y stretch.
export function backgroundCanvas(width: number, height: number) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return { width: 400, height: 240 }
  const scale = Math.min(width / 400, height / 240)
  return { width: width / scale, height: height / scale }
}
