import { describe, it, expect } from 'vitest';
import { parseUnifiedDiff, parseDiffPath, languageFromPath } from '@/lib/utils/diff';

describe('parseUnifiedDiff', () => {
  it('returns empty array for empty input', () => {
    expect(parseUnifiedDiff('')).toEqual([]);
    expect(parseUnifiedDiff('   ')).toEqual([]);
  });

  it('parses a single-file diff with additions and deletions', () => {
    const diff = [
      'diff --git a/src/main.ts b/src/main.ts',
      'index abc1234..def5678 100644',
      '--- a/src/main.ts',
      '+++ b/src/main.ts',
      '@@ -1,3 +1,3 @@',
      ' const a = 1;',
      '-const b = 2;',
      '+const b = 3;',
      ' const c = 4;',
    ].join('\n');

    const result = parseUnifiedDiff(diff);
    expect(result).toHaveLength(1);
    const file = result[0]!;
    expect(file.path).toBe('src/main.ts');
    expect(file.original).toBe('const a = 1;\nconst b = 2;\nconst c = 4;');
    expect(file.modified).toBe('const a = 1;\nconst b = 3;\nconst c = 4;');
  });

  it('parses multi-file diffs', () => {
    const diff = [
      'diff --git a/foo.ts b/foo.ts',
      '--- a/foo.ts',
      '+++ b/foo.ts',
      '@@ -1 +1 @@',
      '-old',
      '+new',
      'diff --git a/bar.py b/bar.py',
      '--- a/bar.py',
      '+++ b/bar.py',
      '@@ -1 +1 @@',
      '-x = 1',
      '+x = 2',
    ].join('\n');

    const result = parseUnifiedDiff(diff);
    expect(result).toHaveLength(2);
    expect(result[0]!.path).toBe('foo.ts');
    expect(result[1]!.path).toBe('bar.py');
  });

  it('handles new file mode (pure additions)', () => {
    const diff = [
      'diff --git a/new.ts b/new.ts',
      'new file mode 100644',
      '--- /dev/null',
      '+++ b/new.ts',
      '@@ -0,0 +1,2 @@',
      '+line one',
      '+line two',
    ].join('\n');

    const result = parseUnifiedDiff(diff);
    expect(result).toHaveLength(1);
    const file = result[0]!;
    expect(file.original).toBe('');
    expect(file.modified).toBe('line one\nline two');
  });

  it('handles deleted file mode (pure deletions)', () => {
    const diff = [
      'diff --git a/old.ts b/old.ts',
      'deleted file mode 100644',
      '--- a/old.ts',
      '+++ /dev/null',
      '@@ -1,2 +0,0 @@',
      '-line one',
      '-line two',
    ].join('\n');

    const result = parseUnifiedDiff(diff);
    expect(result).toHaveLength(1);
    const file = result[0]!;
    expect(file.original).toBe('line one\nline two');
    expect(file.modified).toBe('');
  });

  it('handles rename headers', () => {
    const diff = [
      'diff --git a/old-name.ts b/new-name.ts',
      'similarity index 95%',
      'rename from old-name.ts',
      'rename to new-name.ts',
      '--- a/old-name.ts',
      '+++ b/new-name.ts',
      '@@ -1 +1 @@',
      '-foo',
      '+bar',
    ].join('\n');

    const result = parseUnifiedDiff(diff);
    expect(result).toHaveLength(1);
    expect(result[0]!.path).toBe('new-name.ts');
  });

  it('skips "no newline at end of file" markers', () => {
    const diff = [
      'diff --git a/a.txt b/a.txt',
      '--- a/a.txt',
      '+++ b/a.txt',
      '@@ -1 +1 @@',
      '-hello',
      '\\ No newline at end of file',
      '+world',
      '\\ No newline at end of file',
    ].join('\n');

    const result = parseUnifiedDiff(diff);
    expect(result).toHaveLength(1);
    const file = result[0]!;
    expect(file.original).toBe('hello');
    expect(file.modified).toBe('world');
  });

  it('handles binary file entries gracefully', () => {
    const diff = [
      'diff --git a/image.png b/image.png',
      'Binary files a/image.png and b/image.png differ',
    ].join('\n');

    const result = parseUnifiedDiff(diff);
    expect(result).toHaveLength(1);
    const file = result[0]!;
    expect(file.path).toBe('image.png');
    expect(file.original).toBe('');
    expect(file.modified).toBe('');
  });
});

describe('parseDiffPath', () => {
  it('extracts b-side path', () => {
    expect(parseDiffPath('diff --git a/src/foo.ts b/src/foo.ts')).toBe('src/foo.ts');
  });

  it('returns unknown for malformed lines', () => {
    expect(parseDiffPath('not a diff line')).toBe('unknown');
  });
});

describe('languageFromPath', () => {
  it('maps typescript extensions', () => {
    expect(languageFromPath('src/index.ts')).toBe('typescript');
    expect(languageFromPath('src/App.tsx')).toBe('typescript');
  });

  it('maps javascript extensions', () => {
    expect(languageFromPath('lib/util.js')).toBe('javascript');
    expect(languageFromPath('lib/util.mjs')).toBe('javascript');
    expect(languageFromPath('lib/util.cjs')).toBe('javascript');
    expect(languageFromPath('lib/util.jsx')).toBe('javascript');
  });

  it('maps python', () => {
    expect(languageFromPath('main.py')).toBe('python');
  });

  it('maps special filenames', () => {
    expect(languageFromPath('path/to/Dockerfile')).toBe('dockerfile');
    expect(languageFromPath('path/to/Makefile')).toBe('makefile');
  });

  it('falls back to plaintext', () => {
    expect(languageFromPath('data.xyz')).toBe('plaintext');
  });
});
