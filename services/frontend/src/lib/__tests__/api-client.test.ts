/**
 * Tests for the base apiFetch / ApiError client.
 * These pin the URL construction, header injection, and error path
 * so W5.2/W5.4 refactors can't silently break the contract.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import { apiFetch, ApiError } from '@/lib/api-client'

describe('apiFetch', () => {
  it('prepends /api to the path and returns parsed JSON', async () => {
    server.use(
      http.get('/api/ping', () => HttpResponse.json({ ok: true }))
    )
    const data = await apiFetch<{ ok: boolean }>('/ping')
    expect(data).toEqual({ ok: true })
  })

  it('sends Content-Type: application/json header by default', async () => {
    let receivedContentType: string | null = null
    server.use(
      http.get('/api/header-check', ({ request }) => {
        receivedContentType = request.headers.get('content-type')
        return HttpResponse.json({})
      })
    )
    await apiFetch('/header-check')
    expect(receivedContentType).toBe('application/json')
  })

  it('allows caller headers to be merged in', async () => {
    let receivedAuth: string | null = null
    server.use(
      http.get('/api/auth-check', ({ request }) => {
        receivedAuth = request.headers.get('x-api-key')
        return HttpResponse.json({})
      })
    )
    await apiFetch('/auth-check', { headers: { 'X-Api-Key': 'secret' } })
    expect(receivedAuth).toBe('secret')
  })

  it('throws ApiError with status and body on non-ok response', async () => {
    server.use(
      http.get('/api/fail', () =>
        new HttpResponse('Not Found', { status: 404 })
      )
    )
    await expect(apiFetch('/fail')).rejects.toThrow(ApiError)
  })

  it('ApiError carries status code and body text', async () => {
    server.use(
      http.get('/api/fail-500', () =>
        new HttpResponse('Internal Server Error', { status: 500 })
      )
    )
    try {
      await apiFetch('/fail-500')
      expect.fail('should have thrown')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      const err = e as ApiError
      expect(err.status).toBe(500)
      expect(err.body).toBe('Internal Server Error')
    }
  })

  it('forwards POST body and method', async () => {
    let receivedBody: unknown = null
    server.use(
      http.post('/api/create', async ({ request }) => {
        receivedBody = await request.json()
        return HttpResponse.json({ created: true }, { status: 201 })
      })
    )
    const result = await apiFetch<{ created: boolean }>('/create', {
      method: 'POST',
      body: JSON.stringify({ name: 'test' }),
    })
    expect(result).toEqual({ created: true })
    expect(receivedBody).toEqual({ name: 'test' })
  })
})

describe('VITE_BACKEND_URL support', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('uses VITE_BACKEND_URL as base when set', async () => {
    vi.stubEnv('VITE_BACKEND_URL', 'http://localhost:8010')
    server.use(
      http.get('http://localhost:8010/custom-path', () => HttpResponse.json({ ok: true })),
    )
    const { apiFetch } = await import('@/lib/api-client')
    const data = await apiFetch<{ ok: boolean }>('/custom-path')
    expect(data).toEqual({ ok: true })
  })
})

describe('ApiError', () => {
  it('has the correct name property', () => {
    const err = new ApiError(403, 'Forbidden')
    expect(err.name).toBe('ApiError')
  })

  it('is an instance of Error', () => {
    const err = new ApiError(400, 'Bad Request')
    expect(err).toBeInstanceOf(Error)
  })

  it('message includes status and body', () => {
    const err = new ApiError(422, 'Unprocessable')
    expect(err.message).toContain('422')
    expect(err.message).toContain('Unprocessable')
  })
})
