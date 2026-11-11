import { describe, it, expect } from 'vitest'
import { searchSections, isSectionId, SECTIONS } from './sections'

describe('searchSections', () => {
  it('returns all sections with count 0 for empty query', () => {
    const results = searchSections('')
    expect(results).toHaveLength(SECTIONS.length)
    for (const hit of results) {
      expect(hit.count).toBe(0)
    }
  })

  it('treats whitespace-only as empty', () => {
    const results = searchSections('   ')
    expect(results).toHaveLength(SECTIONS.length)
    for (const hit of results) {
      expect(hit.count).toBe(0)
    }
  })

  it('filters by card title', () => {
    const results = searchSections('Image viewer')
    expect(results.some((h) => h.section.id === 'viewing')).toBe(true)
    const viewing = results.find((h) => h.section.id === 'viewing')!
    expect(viewing.cards.some((c) => c.title === 'Image viewer')).toBe(true)
  })

  it('filters by row label', () => {
    const results = searchSections('Backdrop strength')
    expect(results.some((h) => h.section.id === 'viewing')).toBe(true)
  })

  it('filters by hint text', () => {
    const results = searchSections('per-site pace')
    expect(results.some((h) => h.section.id === 'sources')).toBe(true)
  })

  it('is case-insensitive', () => {
    expect(searchSections('backdrop STRENGTH').some((h) => h.section.id === 'viewing')).toBe(true)
    expect(searchSections('SAFE MODE').some((h) => h.section.id === 'content-filter')).toBe(true)
  })

  it('trims the query', () => {
    expect(searchSections('  retention  ').some((h) => h.section.id === 'trash')).toBe(true)
  })

  it('returns empty array for no match', () => {
    expect(searchSections('zzznotfound')).toHaveLength(0)
  })

  it('reports correct per-section count', () => {
    const results = searchSections('Test')
    const sources = results.find((h) => h.section.id === 'sources')!
    expect(sources.count).toBe(1)

    const library = results.find((h) => h.section.id === 'library')!
    expect(library.count).toBe(2) // Stash + Komga
  })

  it('includes all rows when the card title matches', () => {
    const results = searchSections('Retention')
    const trash = results.find((h) => h.section.id === 'trash')!
    expect(trash.cards[0].rows).toHaveLength(1)
    expect(trash.count).toBe(1)
  })

  it('shows only matching rows when only a row matches', () => {
    const results = searchSections('Lightbox')
    const viewing = results.find((h) => h.section.id === 'viewing')!
    expect(viewing.cards[0].rows).toHaveLength(1)
    expect(viewing.cards[0].rows[0].label).toBe('Lightbox')
    expect(viewing.count).toBe(1)
  })

  it('excludes sections with no matches', () => {
    const results = searchSections('Lightbox')
    expect(results.some((h) => h.section.id === 'sources')).toBe(false)
    expect(results.some((h) => h.section.id === 'about')).toBe(false)
  })
})

describe('isSectionId', () => {
  it('accepts every valid id', () => {
    for (const s of SECTIONS) {
      expect(isSectionId(s.id)).toBe(true)
    }
  })

  it('rejects unknown strings', () => {
    expect(isSectionId('foo')).toBe(false)
    expect(isSectionId('')).toBe(false)
    expect(isSectionId('GENERAL')).toBe(false)
    expect(isSectionId('content_filter')).toBe(false)
  })
})
