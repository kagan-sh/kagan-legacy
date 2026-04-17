import {
  forwardRef,
  type KeyboardEvent,
  type ChangeEvent,
} from 'react';
import { ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';

interface IntentInputProps {
  value: string;
  onChange: (next: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  disabled?: boolean;
  /** ID of the element that describes this input (intent preview / aria-describedby). */
  describedBy?: string;
}

/**
 * Auto-resizing textarea for the home hero input.
 *
 * Single visual line initially, grows to multi-line as the user types.
 * Enter submits; Shift+Enter inserts a newline.
 */
export const IntentInput = forwardRef<HTMLTextAreaElement, IntentInputProps>(
  function IntentInput(
    { value, onChange, onSubmit, placeholder = 'What do you want to do?', disabled, describedBy },
    ref,
  ) {
    const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
      onChange(event.target.value);
    };

    const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault();
        onSubmit();
      }
    };

    const canSubmit = value.trim().length > 0 && !disabled;

    return (
      <div
        className={cn(
          'group relative flex w-full items-end gap-2 bg-[color:var(--surface-1)] px-4 py-3 shadow-[var(--ambient-shadow)]',
          'focus-within:outline focus-within:outline-2 focus-within:outline-[var(--ring)]',
          'transition-colors',
        )}
      >
        <textarea
          ref={ref}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          aria-label="Describe what you want to do"
          aria-describedby={describedBy}
          rows={1}
          className={cn(
            'field-sizing-content min-h-[1.75rem] max-h-[40vh] flex-1 resize-none bg-transparent',
            'text-base text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]',
            'outline-none disabled:cursor-not-allowed disabled:opacity-60',
          )}
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={!canSubmit}
          aria-label="Continue"
          className={cn(
            'inline-flex size-8 shrink-0 items-center justify-center bg-[var(--primary)] text-[var(--primary-foreground)]',
            'transition-[opacity,transform] duration-[var(--motion-fast)]',
            'hover:bg-[var(--primary)]/90 active:scale-95',
            'disabled:bg-[color:var(--surface-2)] disabled:text-[var(--muted-foreground)] disabled:opacity-70',
          )}
        >
          <ArrowRight className="size-4" />
        </button>
      </div>
    );
  },
);
