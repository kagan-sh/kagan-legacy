import * as React from "react"
import { Command as CommandPrimitive } from "cmdk"
import { SearchIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

function Command({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive>) {
  return (
    <CommandPrimitive
      data-slot="command"
      className={cn(
        "flex h-full w-full flex-col overflow-hidden border border-[color:var(--border-subtle)] bg-[var(--card)] text-[var(--card-foreground)] shadow-[var(--ambient-shadow)]",
        className
      )}
      {...props}
    />
  )
}

function CommandDialog({
  title = "Quick Actions",
  description = "Search actions, tasks, and navigation...",
  children,
  className,
  showCloseButton = true,
  ...props
}: React.ComponentProps<typeof Dialog> & {
  title?: string
  description?: string
  className?: string
  showCloseButton?: boolean
}) {
  return (
    <Dialog {...props}>
      <DialogHeader className="sr-only">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <DialogContent
        className={cn(
          "overflow-hidden border-[color:var(--border-subtle)] bg-[var(--card)] p-0 shadow-[var(--ambient-shadow)] sm:max-w-2xl",
          className,
        )}
        overlayClassName="bg-[var(--surface-overlay)] backdrop-blur-sm"
        showCloseButton={showCloseButton}
      >
        <Command className="**:data-[slot=command-input-wrapper]:h-12 [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-3 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:tracking-[0.08em] [&_[cmdk-group-heading]]:text-muted-foreground/90 [&_[cmdk-group]]:px-2 [&_[cmdk-group]:not([hidden])_~[cmdk-group]]:pt-1 [&_[cmdk-input-wrapper]_svg]:h-4 [&_[cmdk-input-wrapper]_svg]:w-4 [&_[cmdk-input]]:h-12 [& [&_[cmdk-item]]:px-3 [&_[cmdk-item]]:py-2.5 [&_[cmdk-item]]:text-[15px] [&_[cmdk-item]_svg]:h-4 [&_[cmdk-item]_svg]:w-4">
          {children}
        </Command>
      </DialogContent>
    </Dialog>
  )
}

function CommandInput({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Input>) {
  return (
    <div
      data-slot="command-input-wrapper"
      className="sticky top-0 z-10 flex h-12 items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:color-mix(in_oklab,var(--surface-1)_76%,var(--card))] px-3 transition-[background-color,border-color,box-shadow] focus-within:border-[color:color-mix(in_oklab,var(--primary)_36%,var(--panel-border))] focus-within:bg-[color:color-mix(in_oklab,var(--surface-1)_84%,var(--card))]"
    >
      <SearchIcon className="size-4 shrink-0 opacity-70" />
      <CommandPrimitive.Input
        data-slot="command-input"
        className={cn(
          "flex h-10 w-full border-0 bg-transparent py-3 text-sm outline-none shadow-none placeholder:text-muted-foreground/80 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-0 focus-visible:shadow-none",
          className
        )}
        {...props}
      />
    </div>
  )
}

function CommandList({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.List>) {
  return (
    <CommandPrimitive.List
      data-slot="command-list"
      className={cn(
        "max-h-[min(70vh,32rem)] scroll-py-2 overflow-x-hidden overflow-y-auto px-1.5 pb-2",
        className
      )}
      {...props}
    />
  )
}

function CommandEmpty({
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Empty>) {
  return (
    <CommandPrimitive.Empty
      data-slot="command-empty"
      className="py-6 text-center text-sm"
      {...props}
    />
  )
}

function CommandGroup({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Group>) {
  return (
    <CommandPrimitive.Group
      data-slot="command-group"
      className={cn(
        "overflow-hidden p-1 text-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function CommandSeparator({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Separator>) {
  return (
    <CommandPrimitive.Separator
      data-slot="command-separator"
      className={cn("-mx-1 h-px bg-border", className)}
      {...props}
    />
  )
}

function CommandItem({
  className,
  ...props
}: React.ComponentProps<typeof CommandPrimitive.Item>) {
  return (
    <CommandPrimitive.Item
      data-slot="command-item"
      className={cn(
        "relative flex cursor-default items-center gap-2 px-3 py-2 text-sm outline-hidden select-none transition-colors data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50 data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4 [&_svg:not([class*='text-'])]:text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

function CommandShortcut({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <span
      data-slot="command-shortcut"
      className={cn(
        "ml-auto text-xs tracking-widest text-muted-foreground",
        className
      )}
      {...props}
    />
  )
}

export {
  Command,
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandShortcut,
  CommandSeparator,
}
