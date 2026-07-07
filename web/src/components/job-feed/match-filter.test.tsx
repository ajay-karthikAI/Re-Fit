/**
 * The min_score slider narrows the matches query: dragging the bar up drops
 * postings below the threshold, dragging it down brings them back. Drives the
 * range input with fireEvent and asserts on the render-prop output so the test
 * exercises the exact slider → filtered-matches wiring the feed relies on.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PostingMatch } from "@/lib/api";
import { MatchFilter, filterMatchesByScore } from "@/components/job-feed/match-filter";

function match(id: string, score: number): PostingMatch {
  return {
    posting_id: id,
    title: `Role ${id}`,
    company_name: "Acme",
    location: "Remote",
    department: "ML",
    url: `https://x/${id}`,
    posted_at: "2026-07-01T00:00:00Z",
    score,
    missing_terms: [],
    computed_at: "2026-07-02T00:00:00Z"
  };
}

const MATCHES = [match("a", 92), match("b", 71), match("c", 54)];

describe("filterMatchesByScore", () => {
  it("keeps only matches at or above the threshold", () => {
    expect(filterMatchesByScore(MATCHES, 70).map((m) => m.posting_id)).toEqual(["a", "b"]);
    expect(filterMatchesByScore(MATCHES, 100)).toEqual([]);
    expect(filterMatchesByScore(MATCHES, 0)).toHaveLength(3);
  });
});

describe("MatchFilter slider", () => {
  it("re-queries the shown matches as the min_score slider moves", () => {
    render(
      <MatchFilter matches={MATCHES} initialMinScore={50}>
        {(filtered) => <div data-testid="ids">{filtered.map((m) => m.posting_id).join(",")}</div>}
      </MatchFilter>
    );

    // Starts at the search's floor (50) → all three visible.
    expect(screen.getByTestId("ids")).toHaveTextContent("a,b,c");
    expect(screen.getByTestId("match-count")).toHaveTextContent("3 of 3 matches");

    const slider = screen.getByLabelText("Minimum score");

    // Raise the bar to 80 → only the 92-scorer survives.
    fireEvent.change(slider, { target: { value: "80" } });
    expect(screen.getByTestId("ids")).toHaveTextContent("a");
    expect(screen.getByTestId("ids")).not.toHaveTextContent("b");
    expect(screen.getByTestId("match-count")).toHaveTextContent("1 of 3 matches");
    expect(screen.getByTestId("min-score-value")).toHaveTextContent("80");

    // Lower it to 60 → the 71-scorer comes back.
    fireEvent.change(slider, { target: { value: "60" } });
    expect(screen.getByTestId("ids")).toHaveTextContent("a,b");
    expect(screen.getByTestId("match-count")).toHaveTextContent("2 of 3 matches");
  });
});
