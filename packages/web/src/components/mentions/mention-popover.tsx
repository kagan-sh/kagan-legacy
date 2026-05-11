/**
 * MentionPopover — wraps any <textarea> and opens a mention typeahead on `#`.
 *
 * - Listens for `#` at word-start (previous char is whitespace or beginning of text).
 * - Debounces 200ms, fetches from /api/mentions/search.
 * - Arrow keys + Enter/Tab select, Esc closes, Backspace past `#` closes.
 */
import React, {
  cloneElement,
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react';
import { apiClient } from '@/lib/api/client';
import type { Mention } from '@kagan/shared-api-client';

const DEBOUNCE_MS = 200;

interface MentionPopoverProps {
  projectId: string;
  children: React.ReactElement<React.TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: React.Ref<HTMLTextAreaElement> }>;
}

export interface MentionPopoverHandle {
  focus: () => void;
}

export const MentionPopover = forwardRef<MentionPopoverHandle, MentionPopoverProps>(
  function MentionPopover({ projectId, children }, ref) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    const [open, setOpen] = useState(false);
    const [mentions, setMentions] = useState<Mention[]>([]);
    const [activeIndex, setActiveIndex] = useState(0);
    const [anchorOffset, setAnchorOffset] = useState<number | null>(null);

    const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

    useImperativeHandle(ref, () => ({
      focus() {
        textareaRef.current?.focus();
      },
    }));

    const close = useCallback(() => {
      setOpen(false);
      setMentions([]);
      setAnchorOffset(null);
    }, []);

    const fetchMentions = useCallback(
      (query: string) => {
        if (debounceTimer.current !== null) clearTimeout(debounceTimer.current);
        debounceTimer.current = setTimeout(() => {
          apiClient
            .searchMentions({ projectId, q: query, limit: 10 })
            .then((results) => {
              setMentions(results);
              setActiveIndex(0);
            })
            .catch(() => {});
        }, DEBOUNCE_MS);
      },
      [projectId],
    );

    const insertMention = useCallback(
      (mention: Mention) => {
        const el = textareaRef.current;
        if (!el || anchorOffset === null) return;

        const cursor = el.selectionStart ?? el.value.length;
        // anchorOffset points to char AFTER `#`, so slice before includes `#`
        const before = el.value.slice(0, anchorOffset - 1); // exclude `#`
        const after = el.value.slice(cursor);
        const inserted = `${mention.id} `;
        const next = `${before}${inserted}${after}`;
        const nextCursor = before.length + inserted.length;

        // Trigger React-controlled onChange
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          'value',
        )?.set;
        nativeInputValueSetter?.call(el, next);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.setSelectionRange(nextCursor, nextCursor);
        close();
      },
      [anchorOffset, close],
    );

    const handleKeyDown = useCallback(
      (e: KeyboardEvent) => {
        if (!open) return;
        switch (e.key) {
          case 'ArrowDown':
            e.preventDefault();
            setActiveIndex((i) => Math.min(i + 1, mentions.length - 1));
            break;
          case 'ArrowUp':
            e.preventDefault();
            setActiveIndex((i) => Math.max(i - 1, 0));
            break;
          case 'Enter':
          case 'Tab': {
            const m = mentions[activeIndex];
            if (m) {
              e.preventDefault();
              insertMention(m);
            }
            break;
          }
          case 'Escape':
            e.preventDefault();
            close();
            break;
          case 'Backspace': {
            // Close if cursor is at or before the # anchor
            const el = textareaRef.current;
            if (el && anchorOffset !== null && (el.selectionStart ?? 0) <= anchorOffset - 1) {
              close();
            }
            break;
          }
        }
      },
      [open, mentions, activeIndex, anchorOffset, insertMention, close],
    );

    const handleInput = useCallback(() => {
      const el = textareaRef.current;
      if (!el) return;

      const cursor = el.selectionStart ?? 0;
      const value = el.value;

      // Walk back from cursor to find `#` at word-start
      let hashPos = -1;
      for (let i = cursor - 1; i >= 0; i--) {
        const ch = value[i];
        if (ch === '#') {
          const prev = value[i - 1];
          if (i === 0 || prev === ' ' || prev === '\n' || prev === '\t') {
            hashPos = i;
          }
          break;
        }
        // Any whitespace between cursor and potential # aborts
        if (ch === ' ' || ch === '\n' || ch === '\t') break;
      }

      if (hashPos === -1) {
        if (open) close();
        return;
      }

      const query = value.slice(hashPos + 1, cursor);
      setAnchorOffset(hashPos + 1); // position of first char after `#`
      setOpen(true);
      fetchMentions(query);
    }, [open, close, fetchMentions]);

    // Attach listeners to the underlying textarea
    useEffect(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.addEventListener('input', handleInput);
      el.addEventListener('keydown', handleKeyDown);
      return () => {
        el.removeEventListener('input', handleInput);
        el.removeEventListener('keydown', handleKeyDown);
      };
    }, [handleInput, handleKeyDown]);

    // Close on outside click
    useEffect(() => {
      if (!open) return;
      const handler = (e: MouseEvent) => {
        if (!containerRef.current?.contains(e.target as Node)) close();
      };
      document.addEventListener('mousedown', handler);
      return () => document.removeEventListener('mousedown', handler);
    }, [open, close]);

    const sourceIcon = (source: 'kagan' | 'github') =>
      source === 'kagan' ? '◆' : '↗';

    return (
      <div ref={containerRef} className="relative">
        {cloneElement(children, { ref: textareaRef } as React.HTMLAttributes<HTMLTextAreaElement> & { ref: React.Ref<HTMLTextAreaElement> })}

        {open && mentions.length > 0 && (
          <div
            role="listbox"
            aria-label="Mention suggestions"
            className="absolute bottom-full left-0 z-50 mb-1 min-w-[18rem] max-w-[28rem] overflow-hidden border border-[color:var(--border-subtle)] bg-[var(--popover)] shadow-[var(--ambient-shadow)]"
          >
            {mentions.map((m, i) => (
              <button
                key={m.id}
                type="button"
                role="option"
                aria-selected={i === activeIndex}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm ${
                  i === activeIndex
                    ? 'bg-[var(--accent)] text-[var(--accent-foreground)]'
                    : 'hover:bg-[var(--accent)] hover:text-[var(--accent-foreground)]'
                }`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertMention(m);
                }}
                onMouseEnter={() => setActiveIndex(i)}
              >
                <span className="shrink-0 text-xs" aria-hidden>
                  {sourceIcon(m.source)}
                </span>
                <span className="font-mono text-xs text-[var(--muted-foreground)] shrink-0">
                  {m.id}
                </span>
                <span className="min-w-0 truncate">{m.title}</span>
                {m.state ? (
                  <span className="ml-auto shrink-0 text-xs text-[var(--muted-foreground)]">
                    {m.state}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  },
);
