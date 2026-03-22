import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { LauncherBackend } from '@/lib/utils/editor-links';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const LAUNCHER_BACKENDS: readonly LauncherBackend[] = [
  'tmux',
  'nvim',
  'vscode',
  'cursor',
  'windsurf',
  'kiro',
  'antigravity',
];

export function asBool(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined) return fallback;
  return !['0', 'false', 'no', 'off'].includes(value.trim().toLowerCase());
}

export function normalizeLauncher(value: string | null | undefined): LauncherBackend {
  if (!value) return 'vscode';
  const normalized = value.trim().toLowerCase();
  return LAUNCHER_BACKENDS.includes(normalized as LauncherBackend)
    ? (normalized as LauncherBackend)
    : 'vscode';
}

export function quoteShell(value: string): string {
  return `"${value.replace(/["\\$`]/g, '\\$&')}"`;
}
