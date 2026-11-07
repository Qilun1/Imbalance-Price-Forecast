import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

/**
 * DESIGN.md pills. `primary` is the action blue: at most one per view, for the decisive action.
 * Everything else is stone. Press feedback is the prompt's scale(0.97).
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-full border border-transparent font-medium whitespace-nowrap select-none transition-[color,background-color,opacity,transform] duration-150 ease-out active:not-disabled:scale-[0.97] disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary: "bg-action text-on-action hover:bg-action-hover",
        secondary: "bg-stone text-on-stone hover:bg-stone-hover",
        outline: "border-stone bg-transparent text-stone hover:bg-fill aria-expanded:bg-fill",
        ghost: "text-stone hover:bg-fill aria-expanded:bg-fill",
        destructive: "bg-error-bg text-error-text hover:bg-error-bg/70",
        link: "text-stone underline underline-offset-4 hover:text-ink",
      },
      size: {
        default: "h-8 gap-1.5 px-3 text-sm has-data-[icon=inline-end]:pr-2.5 has-data-[icon=inline-start]:pl-2.5",
        xs: "h-6 gap-1 px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1 px-2.5 text-xs [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-2 px-4 text-base",
        icon: "size-8",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "secondary",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
