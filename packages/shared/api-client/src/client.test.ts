// Simple type-checking tests for the shared API client
// Run with: pnpm exec tsc --noEmit src/client.test.ts

import type {
  KaganApiClient,
  SSEManager,
  ApiError,
  SSEError,
  ConfigurationError,
  WireTask,
  WireEvent,
  SSEMessage,
  KaganClientConfig,
} from "./index";

// Type tests - these should compile without errors
type TestApiClient = InstanceType<typeof KaganApiClient>;
type TestSSEManager = InstanceType<typeof SSEManager>;
type TestApiError = InstanceType<typeof ApiError>;
type TestSSEError = InstanceType<typeof SSEError>;
type TestConfigError = InstanceType<typeof ConfigurationError>;

// Test that KaganClientConfig has correct shape
const testConfig: KaganClientConfig = {
  baseUrl: "localhost:8765",
  protocol: "http",
  token: "test-token",
  clientType: "test",
};

// Verify error type guards exist
declare const error: unknown;
if (ApiError.isApiError(error)) {
  const status: number = error.status;
  const detail: string = error.detail;
  const errorCode: string | null = error.errorCode;
  const isConnection: boolean = error.isConnectionError();
  const isAuth: boolean = error.isAuthError();
  const isNotFound: boolean = error.isNotFound();
}

console.log("Type tests passed!");
