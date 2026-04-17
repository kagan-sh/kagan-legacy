import * as React from "react"

import { focusRing } from "@/lib/a11y/focus-ring"
import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full border border-input bg-[color:var(--surface-1)] px-3 py-2 text-base shadow-[var(--inset-shadow)] transition-[border-color,color,box-shadow,background-color] outline-none placeholder:text-muted-foreground focus-visible:border-ring disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 md:text-sm dark:aria-invalid:ring-destructive/40",
        focusRing,
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
