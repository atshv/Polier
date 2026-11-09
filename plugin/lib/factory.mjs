// Read-only view of the factory line for the live context: factory.json of the
// project plus the package catalog. Evidence checks and every write stay in
// core/factory.py (tools/factory.py); this file only answers "where is the
// project and what is open" fast enough to run on every model step.

import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

export const FACTORY = 'factory.json'
const RESOLVED = new Set(['done', 'deferred', 'na'])

let catalogCache

/** The package catalog (factory/catalog.json), read once. */
export function loadCatalog(packageDir) {
  if (catalogCache?.dir === packageDir) return catalogCache.value
  const value = JSON.parse(readFileSync(path.join(packageDir, 'factory', 'catalog.json'), 'utf8'))
  catalogCache = { dir: packageDir, value }
  return value
}

/** factory.json of a project, or undefined when it has none or it does not parse. */
export function loadFactory(root) {
  const file = path.join(String(root), FACTORY)
  if (!existsSync(file)) return undefined
  try {
    const data = JSON.parse(readFileSync(file, 'utf8'))
    return data && typeof data === 'object' && !Array.isArray(data) ? data : undefined
  } catch {
    return undefined
  }
}

/**
 * Where the line stands: the current station with its open items, and the
 * progress of every station. Undefined without factory.json.
 */
export function factoryView(root, packageDir) {
  const data = loadFactory(root)
  if (!data) return undefined
  const catalog = loadCatalog(packageDir)
  const items = data.items && typeof data.items === 'object' ? data.items : {}
  const stations = data.stations && typeof data.stations === 'object' ? data.stations : {}
  const order = catalog.stations.map((s) => s.id)
  const current = order.find((id) => stations[id]?.status !== 'done')
  const byStation = Object.fromEntries(order.map((id) => [id, []]))
  for (const item of catalog.items) {
    if (items[item.id]) byStation[item.station]?.push({ ...item, state: items[item.id] })
  }
  const resolved = Object.values(items).filter((entry) => RESOLVED.has(entry?.status)).length
  const station = current ? catalog.stations.find((s) => s.id === current) : undefined
  const open = current ? byStation[current].filter((item) => item.state?.status === 'open') : []
  return {
    platforms: Array.isArray(data.platforms) ? data.platforms : [],
    current,
    index: current ? order.indexOf(current) + 1 : order.length,
    total: order.length,
    station,
    open,
    resolved,
    count: Object.keys(items).length,
    stations: order.map((id) => ({
      id,
      status: stations[id]?.status ?? 'pending',
      done: byStation[id].filter((item) => RESOLVED.has(item.state?.status)).length,
      items: byStation[id].length,
    })),
  }
}
