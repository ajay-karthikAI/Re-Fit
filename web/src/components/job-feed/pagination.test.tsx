/**
 * The feed pager shows 10 postings per page: NEXT advances to the following
 * 10, PREV walks back, and the buttons disable at either end. When the list
 * shrinks under the current page (the min-score slider narrowing matches),
 * the pager snaps back into range instead of stranding an empty page.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  FEED_PAGE_SIZE,
  Pagination,
  pageCount,
  pageSlice
} from "@/components/job-feed/pagination";

const ITEMS = Array.from({ length: 25 }, (_, i) => `item-${i + 1}`);

describe("pageCount / pageSlice", () => {
  it("splits a list into pages of 10", () => {
    expect(FEED_PAGE_SIZE).toBe(10);
    expect(pageCount(25)).toBe(3);
    expect(pageCount(10)).toBe(1);
    expect(pageCount(0)).toBe(1);
    expect(pageSlice(ITEMS, 1)).toHaveLength(10);
    expect(pageSlice(ITEMS, 3)).toEqual(["item-21", "item-22", "item-23", "item-24", "item-25"]);
    expect(pageSlice(ITEMS, 4)).toEqual([]);
  });
});

describe("Pagination", () => {
  it("shows 10 items per page and pages forward and back", () => {
    render(
      <Pagination items={ITEMS}>
        {(pageItems) => <div data-testid="ids">{pageItems.join(",")}</div>}
      </Pagination>
    );

    expect(screen.getByTestId("ids")).toHaveTextContent("item-1,");
    expect(screen.getByTestId("ids")).not.toHaveTextContent("item-11");
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("PAGE 1 OF 3");
    expect(screen.getByTestId("page-prev")).toBeDisabled();

    fireEvent.click(screen.getByTestId("page-next"));
    expect(screen.getByTestId("ids")).toHaveTextContent("item-11");
    expect(screen.getByTestId("ids")).not.toHaveTextContent("item-21");
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("PAGE 2 OF 3");

    fireEvent.click(screen.getByTestId("page-next"));
    expect(screen.getByTestId("ids")).toHaveTextContent("item-21");
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("PAGE 3 OF 3");
    expect(screen.getByTestId("page-next")).toBeDisabled();

    fireEvent.click(screen.getByTestId("page-prev"));
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("PAGE 2 OF 3");
  });

  it("hides the pager when everything fits on one page", () => {
    render(
      <Pagination items={ITEMS.slice(0, 10)}>
        {(pageItems) => <div data-testid="ids">{pageItems.join(",")}</div>}
      </Pagination>
    );
    expect(screen.queryByTestId("page-indicator")).toBeNull();
  });

  it("snaps back into range when the list shrinks under the current page", () => {
    const { rerender } = render(
      <Pagination items={ITEMS}>
        {(pageItems) => <div data-testid="ids">{pageItems.join(",")}</div>}
      </Pagination>
    );
    fireEvent.click(screen.getByTestId("page-next"));
    fireEvent.click(screen.getByTestId("page-next"));
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("PAGE 3 OF 3");

    rerender(
      <Pagination items={ITEMS.slice(0, 12)}>
        {(pageItems) => <div data-testid="ids">{pageItems.join(",")}</div>}
      </Pagination>
    );
    expect(screen.getByTestId("page-indicator")).toHaveTextContent("PAGE 2 OF 2");
    expect(screen.getByTestId("ids")).toHaveTextContent("item-11,item-12");
  });
});
