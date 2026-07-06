import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Unmount and clear the DOM after each test. Without globals:true, Testing
// Library's automatic cleanup does not run, so renders would accumulate.
afterEach(() => {
  cleanup();
});
