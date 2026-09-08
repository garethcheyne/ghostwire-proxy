'use client'

import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * The app's shared modal.
 *
 * Built on Radix's dialog primitives so every dialog gets, for free, the things
 * the previous hand-rolled `fixed inset-0` divs did not have:
 *
 *  - the backdrop is portalled to document.body, so it always covers the whole
 *    viewport instead of being clipped by whatever ancestor it was rendered in;
 *  - background scroll is locked while the dialog is open;
 *  - Escape closes it, focus is trapped inside it and restored on close.
 */

const sizes = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
  '4xl': 'max-w-4xl',
  '5xl': 'max-w-5xl',
} as const

export type ModalSize = keyof typeof sizes

interface ModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  size?: ModalSize
  className?: string
  children: React.ReactNode
  /** Set false for flows that must not be dismissed mid-way (e.g. issuing a cert). */
  dismissible?: boolean
  showCloseButton?: boolean
  /**
   * Accessible name for dialogs that render their own heading markup instead of
   * a ModalTitle. Radix requires every dialog to have a title; this supplies a
   * screen-reader-only one so those dialogs stay accessible without changing
   * their visible layout.
   */
  srTitle?: string
}

export function Modal({
  open,
  onOpenChange,
  size = 'lg',
  className,
  children,
  dismissible = true,
  showCloseButton = true,
  srTitle,
}: ModalProps) {
  const block = (e: Event | React.SyntheticEvent) => {
    if (!dismissible) e.preventDefault()
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-50 bg-black/50',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
          )}
        />
        <DialogPrimitive.Content
          // Descriptions are optional here; without this Radix warns for every
          // dialog that doesn't render one.
          aria-describedby={undefined}
          onEscapeKeyDown={block}
          onPointerDownOutside={block}
          onInteractOutside={block}
          className={cn(
            'fixed left-1/2 top-1/2 z-50 flex -translate-x-1/2 -translate-y-1/2 flex-col',
            'w-[calc(100%-2rem)] max-h-[calc(100dvh-2rem)] overflow-hidden',
            'rounded-xl border border-border bg-card shadow-xl',
            'data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95',
            'data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
            sizes[size],
            className,
          )}
        >
          {srTitle && (
            <ModalTitle className="sr-only">{srTitle}</ModalTitle>
          )}
          {children}
          {showCloseButton && (
            <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none">
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </DialogPrimitive.Close>
          )}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

/** Non-scrolling header. Should contain a ModalTitle. */
export function ModalHeader({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn('shrink-0 border-b border-border px-6 py-4 pr-12', className)}>
      {children}
    </div>
  )
}

export const ModalTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn('text-lg font-semibold leading-none tracking-tight', className)}
    {...props}
  />
))
ModalTitle.displayName = 'ModalTitle'

export const ModalDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
))
ModalDescription.displayName = 'ModalDescription'

/** The only scrolling region, so the header and footer stay put. */
export function ModalBody({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn('min-h-0 flex-1 overflow-y-auto px-6 py-4', className)}>{children}</div>
  )
}

export function ModalFooter({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        'shrink-0 flex flex-col-reverse gap-3 border-t border-border px-6 py-4 sm:flex-row sm:justify-end',
        className,
      )}
    >
      {children}
    </div>
  )
}

export { DialogPrimitive as ModalPrimitive }
