import type { IconName } from '../components/Icon.svelte'

export type SectionId =
  | 'general'
  | 'viewing'
  | 'content-filter'
  | 'discover'
  | 'rules'
  | 'sources'
  | 'library'
  | 'save-folders'
  | 'trash'
  | 'update'
  | 'logs'
  | 'about'

export type Group = 'Personal' | 'Library' | 'System'

export interface OptionRow {
  label: string
  hint: string
}

export interface OptionCard {
  title: string
  rows: OptionRow[]
}

export interface Section {
  id: SectionId
  title: string
  group: Group
  later: boolean
  cards: OptionCard[]
}

export const SECTIONS: Section[] = [
  {
    id: 'general',
    title: 'General',
    group: 'Personal',
    later: true,
    cards: [{ title: 'Coming later', rows: [] }],
  },
  {
    id: 'viewing',
    title: 'Viewing',
    group: 'Personal',
    later: false,
    cards: [
      {
        title: 'Image viewer',
        rows: [
          { label: 'Backdrop strength', hint: '0\u2013100, 0 is plain dark' },
          { label: 'Wall overlay', hint: 'on/off' },
          { label: 'Item page', hint: 'on/off' },
          { label: 'Lightbox', hint: 'on/off' },
        ],
      },
      {
        title: 'Video player',
        rows: [
          { label: 'Autoplay next', hint: 'on/off' },
          { label: 'Default speed', hint: 'playback rate' },
        ],
      },
      {
        title: 'Lists',
        rows: [{ label: 'Infinite scroll', hint: 'next page loads near the end' }],
      },
    ],
  },
  {
    id: 'content-filter',
    title: 'Content filter',
    group: 'Personal',
    later: false,
    cards: [
      {
        title: 'Content filter',
        rows: [
          { label: 'Safe mode', hint: 'SFW filter' },
          { label: 'Allow blurred tags in safe mode', hint: 'warn-list posts stay blurred, never hidden' },
          { label: 'Reveal delay', hint: 'seconds before revealing' },
        ],
      },
    ],
  },
  {
    id: 'discover',
    title: 'Discover',
    group: 'Personal',
    later: false,
    cards: [
      {
        title: 'Sites in the rail',
        rows: [{ label: 'Show in rail', hint: 'per-site on/off' }],
      },
    ],
  },
  {
    id: 'rules',
    title: 'Rules',
    group: 'Library',
    later: false,
    cards: [
      {
        title: 'Rules',
        rows: [{ label: 'Rule list', hint: 'manage rules' }],
      },
    ],
  },
  {
    id: 'sources',
    title: 'Sources',
    group: 'Library',
    later: false,
    cards: [
      {
        title: 'Downloads',
        rows: [{ label: 'Seconds between requests', hint: 'per-site pace' }],
      },
      {
        title: 'Site access',
        rows: [
          { label: 'Test', hint: 'test connection' },
          { label: 'Address', hint: 'site URL' },
          { label: 'Key', hint: 'API key or cookies' },
        ],
      },
    ],
  },
  {
    id: 'library',
    title: 'Library',
    group: 'Library',
    later: false,
    cards: [
      {
        title: 'Stash',
        rows: [
          { label: 'Status', hint: 'connection status' },
          { label: 'Test', hint: 'test connection' },
        ],
      },
      {
        title: 'Komga',
        rows: [
          { label: 'Status', hint: 'connection status' },
          { label: 'Test', hint: 'test connection' },
        ],
      },
      {
        title: 'Status',
        rows: [
          { label: 'Health', hint: 'Stash, Komga, database, mounts, sites' },
        ],
      },
    ],
  },
  {
    id: 'save-folders',
    title: 'Save folders',
    group: 'Library',
    later: false,
    cards: [
      {
        title: 'Save folders',
        rows: [
          { label: 'Default folder', hint: 'Stash folder for saved posts' },
          { label: 'Per-site folder', hint: 'optional override per site' },
        ],
      },
    ],
  },
  {
    id: 'trash',
    title: 'Trash',
    group: 'Library',
    later: false,
    cards: [
      {
        title: 'Retention',
        rows: [{ label: 'Retention days', hint: 'auto-purge after N days' }],
      },
    ],
  },
  {
    id: 'update',
    title: 'Update',
    group: 'System',
    later: false,
    cards: [{ title: 'Update', rows: [{ label: 'Installed', hint: 'version and channel' }, { label: 'Latest', hint: 'newest release' }, { label: 'Channel', hint: 'main or dev' }, { label: 'Automatic check', hint: 'check for updates automatically' }] }],
  },
  {
    id: 'logs',
    title: 'Logs',
    group: 'System',
    later: false,
    cards: [
      {
        title: 'Logging',
        rows: [
          { label: 'Debug', hint: 'Adds detail. Off by default. Turn off when done.' },
          { label: 'Kept', hint: '7 days, one file per day' },
        ],
      },
      {
        title: 'Log viewer',
        rows: [
          { label: 'Day', hint: 'pick a day' },
          { label: 'Level', hint: 'error, warning, info, debug' },
        ],
      },
    ],
  },
  {
    id: 'about',
    title: 'About',
    group: 'System',
    later: false,
    cards: [
      {
        title: 'Version',
        rows: [{ label: 'Pearlie', hint: 'version info' }],
      },
      {
        title: 'Links',
        rows: [{ label: 'Project', hint: 'external links' }],
      },
    ],
  },
]

export interface SearchHit {
  section: Section
  count: number
  cards: OptionCard[]
}

/** True when a row's label or hint contains the (lower-cased) query. */
export function rowMatches(row: OptionRow, q: string): boolean {
  return (
    row.label.toLowerCase().includes(q) || row.hint.toLowerCase().includes(q)
  )
}

/**
 * Filter sections by a case-insensitive substring match on card title,
 * row label, or row hint.  Empty / whitespace-only query returns every
 * section with `count: 0` (sentinel meaning "no filter applied").
 */
export function searchSections(query: string): SearchHit[] {
  const q = query.trim().toLowerCase()

  if (q === '') {
    return SECTIONS.map((section) => ({
      section,
      count: 0,
      cards: section.cards,
    }))
  }

  const results: SearchHit[] = []

  for (const section of SECTIONS) {
    let count = 0
    const matchedCards: OptionCard[] = []

    for (const card of section.cards) {
      if (card.title.toLowerCase().includes(q)) {
        count += card.rows.length
        matchedCards.push(card)
      } else {
        const matchedRows = card.rows.filter(
          (r) =>
            r.label.toLowerCase().includes(q) ||
            r.hint.toLowerCase().includes(q),
        )
        if (matchedRows.length > 0) {
          count += matchedRows.length
          matchedCards.push({ title: card.title, rows: matchedRows })
        }
      }
    }

    if (matchedCards.length > 0) {
      results.push({ section, count, cards: matchedCards })
    }
  }

  return results
}

const SECTION_IDS: ReadonlySet<string> = new Set(SECTIONS.map((s) => s.id))

export function isSectionId(s: string): s is SectionId {
  return SECTION_IDS.has(s)
}

export const SECTION_ICONS: Record<SectionId, IconName> = {
  general: 'sliders',
  viewing: 'eye',
  'content-filter': 'eye-off',
  discover: 'star',
  rules: 'rules',
  sources: 'download',
  library: 'library',
  'save-folders': 'bookmark',
  trash: 'trash',
  update: 'refresh',
  logs: 'list',
  about: 'info',
}
