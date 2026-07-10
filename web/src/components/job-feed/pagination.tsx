"use client";

import { type ReactNode, useEffect, useState } from "react";

export const FEED_PAGE_SIZE = 10;

/** Total pages for a list — never 0, so "page 1 of 1" renders for empty lists. */
export function pageCount(total: number, perPage: number = FEED_PAGE_SIZE): number {
  return Math.max(1, Math.ceil(total / perPage));
}

/** Pure slice of one page — extracted so it is testable. */
export function pageSlice<T>(items: T[], page: number, perPage: number = FEED_PAGE_SIZE): T[] {
  return items.slice((page - 1) * perPage, page * perPage);
}

/**
 * Client-side pager over an already-loaded list. Owns the page state and hands
 * the current page's slice to its render prop. Snaps back into range when the
 * list shrinks (e.g. the min-score slider narrows the matches).
 */
export function Pagination<T>({
  items,
  perPage = FEED_PAGE_SIZE,
  children
}: {
  items: T[];
  perPage?: number;
  children: (pageItems: T[]) => ReactNode;
}) {
  const [page, setPage] = useState(1);
  const pages = pageCount(items.length, perPage);
  const current = Math.min(page, pages);

  useEffect(() => {
    setPage((value) => Math.min(value, pageCount(items.length, perPage)));
  }, [items.length, perPage]);

  const goTo = (next: number) => {
    setPage(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const buttonCls =
    "rounded-full border border-silver/[0.18] px-3.5 py-1.5 font-mono text-xs text-accent transition enabled:hover:border-accent/60 disabled:cursor-default disabled:border-silver/10 disabled:text-faint";

  return (
    <div className="space-y-4">
      {children(pageSlice(items, current, perPage))}
      {pages > 1 ? (
        <nav aria-label="Pagination" className="flex items-center justify-between gap-3">
          <button
            type="button"
            data-testid="page-prev"
            onClick={() => goTo(current - 1)}
            disabled={current === 1}
            className={buttonCls}
          >
            ← PREV
          </button>
          <span data-testid="page-indicator" className="font-mono text-xs text-faint">
            PAGE {current} OF {pages}
          </span>
          <button
            type="button"
            data-testid="page-next"
            onClick={() => goTo(current + 1)}
            disabled={current === pages}
            className={buttonCls}
          >
            NEXT →
          </button>
        </nav>
      ) : null}
    </div>
  );
}
