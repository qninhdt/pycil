export const stripCapacity = { 32: 128 } as const

function stripStyles(size: 32) {
  const grid = `.fit-tile-strip-${size} > .fit-tile-grid`
  const base = `${grid}{display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:minmax(0,1fr);height:100%;width:100%}${grid}>.fit-tile{display:none;min-width:0;min-height:0;height:100%}${grid}>.fit-tile:first-child{display:block}`
  return base + Array.from({ length: stripCapacity[size] - 1 }, (_, index) => {
    const count = index + 2
    return `@container pycil-strip-${size} (min-width:${(count - .5) * size}px){${grid}{grid-template-columns:repeat(${count},minmax(0,1fr))}${grid}>.fit-tile:nth-child(${count}){display:block}}`
  }).join('')
}

export const tileStripStyles = { 32: stripStyles(32) }
