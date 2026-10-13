import database from '../../src/lib/api/services/mock/database.json' with { type: 'json' }

import { expect,test } from 'vitest'

import { generateBauhausPattern } from '../../src/lib/bauhaus-pattern'

import { flashcardArtwork,flashcardBackgrounds } from '../../src/lib/flashcard-artwork'

import { backgroundCanvas } from '../../src/lib/background-layout'

import { parseDictionaryWord } from '../../src/lib/api/vocabulary'

test('seeded patterns are deterministic, balanced and extend without changing existing blocks', () => {
  const blocks = generateBauhausPattern('pycil-1923')
  expect(generateBauhausPattern('pycil-1923')).toEqual(blocks)
  expect(generateBauhausPattern('another-seed')).not.toEqual(blocks)
  expect(generateBauhausPattern('pycil-1923', 12)).toEqual(blocks.slice(0, 12))
  expect(generateBauhausPattern('pycil-1923', 40).slice(0, 32)).toEqual(blocks)
  for (let color = 0; color < 4; color++) expect(blocks.filter(block => block.primary === color)).toHaveLength(8)
  for (const [index, block] of blocks.entries()) {
    expect(block.secondary).not.toBe(block.primary)
    expect([0, 90, 180, 270]).toContain(block.rotation)
    if (index) expect(block.motif).not.toBe(blocks[index - 1].motif)
  }
})

test('adaptive background canvases fill arbitrary ratios without cropping or x/y distortion', () => {
  for (const [width, height] of [[400, 240], [1200, 200], [760, 360], [320, 500], [240, 240]]) {
    const canvas = backgroundCanvas(width, height)
    expect(canvas.width).toBeGreaterThanOrEqual(400)
    expect(canvas.height).toBeGreaterThanOrEqual(240)
    expect(canvas.width / canvas.height).toBeCloseTo(width / height, 8)
    expect(width / canvas.width).toBeCloseTo(height / canvas.height, 8)
  }
  expect(backgroundCanvas(0, 0)).toEqual({ width: 400, height: 240 })
})

test('flashcard seeds select only the existing 16 backgrounds, independent of order or deck', () => {
  const senses = database.dictionary.words.map(parseDictionaryWord).flatMap(word => word.senses)
  const artwork = senses.map(sense => flashcardArtwork(sense.id))
  expect(flashcardBackgrounds).toHaveLength(16)
  expect(new Set(flashcardBackgrounds).size).toBe(16)
  expect(new Set(artwork).size).toBeGreaterThan(1)
  for (const sense of [...senses].reverse()) {
    expect(flashcardArtwork(sense.id)).toEqual(artwork[senses.indexOf(sense)])
    expect(flashcardArtwork(String(sense.id))).toEqual(flashcardArtwork(sense.id))
    expect(flashcardBackgrounds).toContain(flashcardArtwork(sense.id))
  }
  const deckLimit = Array.from({ length: 1000 }, (_, index) => flashcardArtwork(index + 1))
  expect(new Set(deckLimit).size).toBe(16)
})
