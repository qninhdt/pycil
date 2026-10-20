import { createHmac } from 'node:crypto'

export function authenticatorCode(secret: string, now = Date.now()) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  const bits = [...secret.toUpperCase().replace(/=+$/, '')].map(character => {
    const value = alphabet.indexOf(character)
    if (value < 0) throw new Error('Authenticator secret has invalid Base32')
    return value.toString(2).padStart(5, '0')
  }).join('')
  const bytes = bits.match(/.{8}/g)
  if (!bytes?.length) throw new Error('Authenticator secret is empty or incomplete')
  const key = Buffer.from(bytes.map(byte => parseInt(byte, 2)))
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(now / 30_000)))
  const digest = createHmac('sha1', key).update(counter).digest()
  const offset = digest[digest.length - 1] & 15
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, '0')
}

