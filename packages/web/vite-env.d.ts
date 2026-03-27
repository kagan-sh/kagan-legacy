/// <reference types="vite/client" />
/// <reference types="@testing-library/jest-dom/vitest" />

// axe-core accessibility matchers for vitest
import type { AxeMatchers } from 'vitest-axe/matchers';
import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers';

declare module 'vitest' {
  interface Assertion<T> extends AxeMatchers, TestingLibraryMatchers<any, T> {}
  interface AsymmetricMatchersContaining extends AxeMatchers, TestingLibraryMatchers<any, any> {}
}
