import type { AttachmentAdapter, CompleteAttachment, PendingAttachment } from "@assistant-ui/react"

const MAX_SOURCE_BYTES = 20_000_000
const MAX_IMAGE_BYTES = 550_000
const IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"])

function canvasBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Could not process image")), "image/jpeg", quality)
  })
}

/** Keep the encoded AG-UI request below the proxy's 1 MB body limit. */
async function prepareImage(file: File): Promise<File> {
  if (!IMAGE_TYPES.has(file.type)) throw new Error("Choose a JPEG, PNG, or WebP image")
  if (file.size > MAX_SOURCE_BYTES) throw new Error("Choose an image under 20 MB")

  const bitmap = await createImageBitmap(file)
  try {
    const canvas = document.createElement("canvas")
    const context = canvas.getContext("2d")
    if (!context) throw new Error("Image processing is unavailable")
    let scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height))
    for (let attempt = 0; attempt < 6; attempt += 1) {
      canvas.width = Math.max(1, Math.round(bitmap.width * scale))
      canvas.height = Math.max(1, Math.round(bitmap.height * scale))
      context.fillStyle = "white"
      context.fillRect(0, 0, canvas.width, canvas.height)
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
      const blob = await canvasBlob(canvas, attempt < 3 ? 0.82 : 0.7)
      if (blob.size <= MAX_IMAGE_BYTES) {
        return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" })
      }
      scale *= 0.75
    }
    throw new Error("This image is too detailed to send. Choose a smaller image")
  } finally {
    bitmap.close()
  }
}

function dataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error("Could not read image"))
    reader.readAsDataURL(file)
  })
}

export function imageAttachmentAdapter(onError: (message: string) => void): AttachmentAdapter {
  return {
    accept: "image/jpeg,image/png,image/webp",
    async add({ file }) {
      try {
        const prepared = await prepareImage(file)
        onError("")
        return {
          id: crypto.randomUUID(),
          type: "image",
          name: file.name,
          file: prepared,
          status: { type: "requires-action", reason: "composer-send" },
        } satisfies PendingAttachment
      } catch (error) {
        onError(error instanceof Error ? error.message : "Could not attach image")
        throw error
      }
    },
    async send(attachment) {
      return {
        id: attachment.id,
        type: "image",
        name: attachment.name,
        contentType: "image/jpeg",
        content: [{ type: "image", image: await dataUrl(attachment.file) }],
        status: { type: "complete" },
      } satisfies CompleteAttachment
    },
    async remove() {},
  }
}
