/**
 * Flatten the small markdown subset our generators emit (bold/italic, dash
 * lists, inline code, links) to plain text. Most ATS textareas paste raw and do
 * not render markdown, so the "Copy as plain text" action ships this instead of
 * leaving literal `**asterisks**` in the applicant's answer.
 */
export function stripMarkdown(markdown: string): string {
  return markdown
    .replace(/\*\*(.+?)\*\*/g, "$1") // bold
    .replace(/\*(.+?)\*/g, "$1") // italic
    .replace(/`([^`]+)`/g, "$1") // inline code
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // links -> link text
    .replace(/^[ \t]{0,3}[-*+][ \t]+/gm, "") // leading list markers (not across newlines)
    .replace(/[ \t]+$/gm, "") // trailing whitespace
    .trim();
}
