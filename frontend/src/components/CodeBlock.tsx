import { useState } from 'react';

import { copyText } from '../lib/clipboard';

interface CodeBlockProps {
  /** The snippet to display, without the language label. */
  code: string;
  /** Short language badge, e.g. "python" or "bash". */
  language?: string;
  /** Optional caption rendered under the block. */
  caption?: string;
  /** Set false for blocks that are not meant to be copied verbatim. */
  copyable?: boolean;
}

export function CodeBlock({ code, language = 'python', caption, copyable = true }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    // Clipboard access can be denied; leave the button un-ticked rather than
    // claiming a copy succeeded.
    if (!(await copyText(code))) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <figure className="code-block">
      <div className="code-block-bar">
        <span className="code-block-lang">{language}</span>
        {copyable && (
          <button
            type="button"
            className="code-block-copy"
            data-copied={copied}
            onClick={copy}
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
        )}
      </div>
      <pre className="code-block-body">
        <code>{code}</code>
      </pre>
      {caption && <figcaption className="code-block-caption">{caption}</figcaption>}
    </figure>
  );
}
