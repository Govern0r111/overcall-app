import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "../lib/utils";

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const el = document.createElement("textarea");
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    el.remove();
  }
};

export const CopyField = ({ value, testId, className }: { value: string; testId: string; className?: string }) => {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    await copyText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };
  return (
    <div className={cn("flex min-w-0 items-center rounded-md border border-border bg-background", className)}>
      <code data-testid={`${testId}-value`} className="min-w-0 flex-1 truncate px-3 py-2 font-mono text-xs">{value}</code>
      <button
        type="button"
        onClick={onCopy}
        data-testid={testId}
        className="flex shrink-0 items-center gap-1.5 border-l border-border px-3 py-2 text-xs font-medium text-primary transition-colors hover:bg-accent"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
};
