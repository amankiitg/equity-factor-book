import { defineConfig } from "vitest/config";

// The Worker's checks and the page's checks, in one run.
//
// The Worker is tested through a pure handler with its JWT check and its R2
// binding injected, so there is no Workers runtime and no network here: what is
// asserted is what the code does, and the runtime supplies the same shapes.
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}", "worker/**/*.test.ts"],
  },
});
