import { readFileSync } from 'node:fs'
import { request } from 'node:http'
import path from 'node:path'
import type { Plugin } from 'vite'

// Development only. The browser never receives the private service credential.
export function workingMemoryPreview(): Plugin {
  return {
    name: 'working-memory-local-review',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = new URL(req.url || '/', 'http://localhost')
        if (!url.pathname.startsWith('/api/working-memory/')) return next()
        const fail = (status: number) => {
          res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
          res.end(JSON.stringify({ error: 'Local read-only preview unavailable' }))
        }
        // Reject cross-origin requests and all mutations, including unknown routes.
        if (req.headers.origin && req.headers.origin !== `http://${req.headers.host}`) return fail(403)
        if (req.method !== 'GET') return fail(405)
        const route = url.pathname.slice('/api/working-memory'.length)
        if (route !== '/review' && route !== '/archive' && !/^\/(sources|archive)\/[a-f0-9]{64}$/.test(route)) return fail(404)
        const allowed = route === '/review' ? ['as_of'] : route === '/archive' ? ['q', 'as_of', 'known_at', 'order', 'limit', 'offset'] : []
        if ([...url.searchParams.keys()].some(key => !allowed.includes(key))) return fail(400)
        try {
          const config = JSON.parse(readFileSync(path.join(server.config.root, 'working-memory/.local/preview-service.json'), 'utf8')) as { port: number; token: string }
          if (!Number.isInteger(config.port) || config.port < 1024 || config.port > 65535 || typeof config.token !== 'string' || config.token.length < 32) return fail(503)
          const upstream = request({ hostname: '127.0.0.1', port: config.port, path: route + url.search, method: 'GET', headers: { Authorization: `Bearer ${config.token}` } }, response => {
            res.writeHead(response.statusCode || 502, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
            response.pipe(res)
            response.on('error', () => res.destroy())
          })
          upstream.setTimeout(10000, () => upstream.destroy(new Error('timeout')))
          upstream.on('error', () => { if (!res.headersSent) fail(503); else res.destroy() })
          res.on('close', () => upstream.destroy())
          upstream.end()
        } catch { fail(503) }
      })
    },
  }
}
