/**
 * Kagan application constants — single source of truth for external URLs and metadata.
 */

export const KAGAN_URLS = {
  /** GitHub repository */
  github: 'https://github.com/kagan-sh/kagan',
  /** MIT License file */
  license: 'https://github.com/kagan-sh/kagan/blob/main/LICENSE',
  /** MakerX — the team behind Kagan */
  makerx: 'https://makerx.com.au',
  /** Documentation site */
  docs: 'https://docs.kagan.sh',
  /** Discord community */
  discord: 'https://discord.gg/dB5AgMwWMy',
  /** PyPI package */
  pypi: 'https://pypi.org/project/kagan/',
  /** Website */
  website: 'https://kagan.sh',
} as const;

export const KAGAN_META = {
  name: 'Kagan',
  tagline: 'AI Coding Agent Orchestrator',
  makerxName: 'MakerX',
  license: 'MIT',
  copyrightYear: new Date().getFullYear(),
} as const;
