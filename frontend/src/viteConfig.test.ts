import src from '../vite.config.ts?raw'
import { describe, it, expect } from 'vitest'

describe('vite.config dev server', () => {
  it('sets port to 2900', () => {
    expect(src).toMatch(/port:\s*2900\b/)
  })
  it('proxies /api to 127.0.0.1:8000', () => {
    expect(src).toContain("'/api': 'http://127.0.0.1:8000'")
  })
  it('does not reference port 5173', () => {
    expect(src).not.toContain('5173')
  })
})
