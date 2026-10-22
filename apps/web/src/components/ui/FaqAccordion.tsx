import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

interface AccordionProps {
  items: Array<{ question: string; answer: ReactNode }>;
}

export function Accordion({ items }: AccordionProps) {
  return (
    <div className="accordion">
      {items.map(({ question, answer }) => (
        <details className="accordion__item" key={question}>
          <summary>
            <span>{question}</span>
            <ChevronDown aria-hidden="true" className="accordion__icon" size={18} />
          </summary>
          <div className="accordion__answer">{answer}</div>
        </details>
      ))}
    </div>
  );
}
