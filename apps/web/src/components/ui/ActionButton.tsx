import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost";

export function buttonClassName(variant: ButtonVariant = "primary"): string {
  return `button button--${variant}`;
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  children: ReactNode;
}

export function Button({ variant = "primary", className = "", children, ...props }: ButtonProps) {
  return (
    <button className={`${buttonClassName(variant)} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}
