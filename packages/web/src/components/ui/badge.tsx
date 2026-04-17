import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { focusRing } from "@/lib/a11y/focus-ring"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  cn(
    "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-[color,box-shadow,border-color,background-color] focus-visible:border-ring aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3",
    focusRing,
  ),
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground [a&]:hover:bg-primary/92",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground [a&]:hover:bg-secondary/90",
        destructive:
          "bg-destructive text-destructive-foreground dark:bg-destructive/60 [a&]:hover:bg-destructive/90",
        outline:
          "border-border text-foreground [a&]:hover:bg-accent",
        ghost: "[a&]:hover:bg-[color:var(--surface-2)] [a&]:hover:text-foreground",
        link: "text-foreground underline-offset-4 [a&]:hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
