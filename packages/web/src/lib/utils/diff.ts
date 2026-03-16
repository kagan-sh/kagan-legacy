/** Pure diff-parsing utilities — zero UI concern. */

export interface ParsedDiffFile {
  path: string;
  original: string;
  modified: string;
}

export const HUNK_META_PREFIXES = [
  'index ',
  '--- ',
  '+++ ',
  'new file mode ',
  'deleted file mode ',
  'old mode ',
  'new mode ',
  'similarity index ',
  'dissimilarity index ',
  'rename from ',
  'rename to ',
  'Binary files ',
];

export function parseDiffPath(line: string): string {
  const match = /^diff --git a\/(.+) b\/(.+)$/.exec(line.trim());
  return match?.[2] ?? 'unknown';
}

function finalizeBlock(
  blocks: ParsedDiffFile[],
  currentPath: string | null,
  originalLines: string[],
  modifiedLines: string[],
): void {
  if (!currentPath) {
    return;
  }

  blocks.push({
    path: currentPath,
    original: originalLines.join('\n'),
    modified: modifiedLines.join('\n'),
  });
}

export function parseUnifiedDiff(diffText: string): ParsedDiffFile[] {
  if (!diffText.trim()) {
    return [];
  }

  const blocks: ParsedDiffFile[] = [];
  let currentPath: string | null = null;
  let originalLines: string[] = [];
  let modifiedLines: string[] = [];

  for (const line of diffText.split('\n')) {
    if (line.startsWith('diff --git ')) {
      finalizeBlock(blocks, currentPath, originalLines, modifiedLines);
      currentPath = parseDiffPath(line);
      originalLines = [];
      modifiedLines = [];
      continue;
    }

    if (!currentPath) {
      continue;
    }

    if (line.startsWith('@@')) {
      continue;
    }

    if (HUNK_META_PREFIXES.some((prefix) => line.startsWith(prefix))) {
      continue;
    }

    if (line === '\\ No newline at end of file') {
      continue;
    }

    if (line.startsWith('+') && !line.startsWith('+++')) {
      modifiedLines.push(line.slice(1));
      continue;
    }

    if (line.startsWith('-') && !line.startsWith('---')) {
      originalLines.push(line.slice(1));
      continue;
    }

    if (line.startsWith(' ')) {
      const content = line.slice(1);
      originalLines.push(content);
      modifiedLines.push(content);
      continue;
    }

    originalLines.push(line);
    modifiedLines.push(line);
  }

  finalizeBlock(blocks, currentPath, originalLines, modifiedLines);
  return blocks;
}

export function languageFromPath(path: string): string {
  const lower = path.toLowerCase();
  const fileName = lower.split('/').at(-1) ?? '';

  if (fileName === 'dockerfile') return 'dockerfile';
  if (fileName === 'makefile') return 'makefile';

  if (lower.endsWith('.ts')) return 'typescript';
  if (lower.endsWith('.tsx')) return 'typescript';
  if (lower.endsWith('.js') || lower.endsWith('.mjs') || lower.endsWith('.cjs')) return 'javascript';
  if (lower.endsWith('.jsx')) return 'javascript';
  if (lower.endsWith('.vue')) return 'html';
  if (lower.endsWith('.svelte')) return 'html';
  if (lower.endsWith('.py')) return 'python';
  if (lower.endsWith('.go')) return 'go';
  if (lower.endsWith('.rs')) return 'rust';
  if (lower.endsWith('.java')) return 'java';
  if (lower.endsWith('.kt')) return 'kotlin';
  if (lower.endsWith('.dart')) return 'dart';
  if (lower.endsWith('.c')) return 'c';
  if (lower.endsWith('.h')) return 'c';
  if (lower.endsWith('.cc') || lower.endsWith('.cpp') || lower.endsWith('.cxx') || lower.endsWith('.hpp')) return 'cpp';
  if (lower.endsWith('.cs')) return 'csharp';
  if (lower.endsWith('.php')) return 'php';
  if (lower.endsWith('.rb')) return 'ruby';
  if (lower.endsWith('.swift')) return 'swift';
  if (lower.endsWith('.scala')) return 'scala';
  if (lower.endsWith('.sql')) return 'sql';
  if (lower.endsWith('.xml')) return 'xml';
  if (lower.endsWith('.toml')) return 'ini';
  if (lower.endsWith('.ini') || lower.endsWith('.cfg') || lower.endsWith('.conf')) return 'ini';
  if (lower.endsWith('.json')) return 'json';
  if (lower.endsWith('.md')) return 'markdown';
  if (lower.endsWith('.yml') || lower.endsWith('.yaml')) return 'yaml';
  if (lower.endsWith('.css')) return 'css';
  if (lower.endsWith('.html')) return 'html';
  if (lower.endsWith('.ps1')) return 'powershell';
  if (lower.endsWith('.bat') || lower.endsWith('.cmd')) return 'bat';
  if (lower.endsWith('.sh')) return 'shell';
  return 'plaintext';
}
