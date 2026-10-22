import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "../lib/utils";

export const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const el = document.createElement("textarea");
    el.value = text;
    el.setAttribute("readonly", "");
    el.style.position = "fixed";
    el.style.opacity = "0";
    document.body.appendChild(el);
    el.select();
    let copiedToClipboard = false;
    try {
      copiedToClipboard = document.execCommand("copy");
    } finally {
      el.remove();
    }
    if (!copiedToClipboard) {
      throw new Error("Copy failed. Select the text and copy it manually.");
    }
  }
};

export const CopyField = ({ value, testId, className }: { value: string; testId: string; className?: string }) => {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  const onCopy = async () => {
    setCopyError("");
    try {
      await copyToClipboard(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch (error) {
      setCopied(false);
      setCopyError(error instanceof Error ? error.message : "Copy failed.");
    }
  };
  return (
    <>
      <div className={cn("flex min-w-0 items-center rounded-md border border-border bg-background", className)}>
        <code data-testid={`${testId}-value`} className="min-w-0 flex-1 truncate px-3 py-2 font-mono text-xs">{value}</code>
        <button
          type="button"
          onClick={onCopy}
          data-testid={testId}
          className="flex shrink-0 items-center gap-1.5 border-l border-border px-3 py-2 text-xs font-medium text-primary transition-colors hover:bg-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      {copyError && <p className="mt-1 text-xs text-destructive" role="alert">{copyError}</p>}
      {copied && <span className="sr-only" role="status">Copied</span>}
    </>
  );
};
