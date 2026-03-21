/// <reference types="vite/client" />

// axe-core accessibility matchers for vitest
import type { AxeMatchers } from 'vitest-axe/matchers';

declare module 'vitest' {
  interface Assertion<T> extends AxeMatchers {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
