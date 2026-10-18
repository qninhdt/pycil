import 'server-only'

import { ImageResponse } from 'next/og'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { publicProfile, publicNode } from './public-server'

const font = readFile(join(process.cwd(), 'src/assets/manrope-social.ttf'))
const mark = readFile(join(process.cwd(), 'public/pycil-mark.svg'), 'base64')

export async function publicSocialImage({ params }: { params: Promise<{ identifier: string; nodeId?: string }> }) {
  const { identifier, nodeId } = await params
  const [profile, node] = await Promise.all([publicProfile(identifier), nodeId ? publicNode(identifier, nodeId) : null])
  const author = profile!.display_name || profile!.handle || 'Pycil learner'
  const title = node?.name || author
  const description = node ? `${node.type === 'reference' ? node.target?.type || 'Collection' : node.type} by ${author}` : profile!.bio || 'Published vocabulary on Pycil'
  return socialImage(title, description)
}

export async function socialImage(title: string, description: string) {
  const [fontData, logo] = await Promise.all([font, mark])
  return new ImageResponse(<div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', width: '100%', height: '100%', padding: 64, background: '#ECF0F1', color: '#2C3E50', fontFamily: 'Manrope' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
      {/* Static bundled artwork only; user-provided URLs never enter image rendering. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`data:image/svg+xml;base64,${logo}`} width={64} height={64} alt="" />
      <span style={{ fontSize: 34 }}>Pycil</span>
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ fontSize: 64, lineHeight: 1.12, maxHeight: 225, overflow: 'hidden', wordBreak: 'break-word' }}>{title.slice(0, 150)}</div>
      <div style={{ fontSize: 28, lineHeight: 1.4, maxHeight: 80, overflow: 'hidden' }}>{description.slice(0, 180)}</div>
    </div>
    <div style={{ display: 'flex', height: 16 }}><div style={{ width: '45%', background: '#E74C3C' }} /><div style={{ width: '35%', background: '#3498DB' }} /><div style={{ width: '20%', background: '#F1C40F' }} /></div>
  </div>, { width: 1200, height: 630, fonts: [{ name: 'Manrope', data: fontData, weight: 700, style: 'normal' }], headers: { 'Cache-Control': 'private, no-store' } })
}
