import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLElement> {
  children: ReactNode;
  as?: "article" | "div" | "section";
}

export function Card({ as: Element = "article", children, className = "", ...props }: CardProps) {
  return (
    <Element className={`card ${className}`.trim()} {...props}>
      {children}
    </Element>
  );
}
