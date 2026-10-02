/**
 * Clipboard writes, shared by the places that copy an identifier.
 *
 * `navigator.clipboard` is unavailable on an insecure origin and can be denied by
 * permissions, so a `textarea` plus `execCommand` fallback is kept for the cases
 * where the modern API throws. Returns whether the copy actually happened, so a
 * caller never claims a copy it did not make.
 */
export async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      return document.execCommand('copy');
    } catch {
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  }
}
