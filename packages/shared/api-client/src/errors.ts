// ============================================================================
// Error Handling
// ============================================================================

export interface ApiErrorDetail {
  field?: string;
  message: string;
  code?: string;
}

/**
 * Typed API error with HTTP status and optional error code.
 * Compatible with both web and VS Code error handling patterns.
 */
export class ApiError extends Error {
  readonly name = "ApiError";

  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly errorCode: string | null = null,
  ) {
    super(detail);
    // Fix prototype chain for instanceof checks
    Object.setPrototypeOf(this, ApiError.prototype);
  }

  /**
   * Type guard to check if an error is an ApiError.
   */
  static isApiError(error: unknown): error is ApiError {
    return error instanceof ApiError || (
      error instanceof Error &&
      "status" in error &&
      typeof (error as ApiError).status === "number"
    );
  }

  /**
   * Check if the error represents a connection failure.
   */
  isConnectionError(): boolean {
    return this.status === 0 || this.status >= 500;
  }

  /**
   * Check if the error represents an authentication failure.
   */
  isAuthError(): boolean {
    return this.status === 401 || this.status === 403;
  }

  /**
   * Check if the error represents a "not found" response.
   */
  isNotFound(): boolean {
    return this.status === 404;
  }

  toJSON(): Record<string, unknown> {
    return {
      name: this.name,
      status: this.status,
      detail: this.detail,
      errorCode: this.errorCode,
      message: this.message,
    };
  }
}

/**
 * Error thrown when SSE connection fails.
 */
export class SSEError extends Error {
  readonly name = "SSEError";

  constructor(
    message: string,
    public readonly cause?: Error,
  ) {
    super(message);
    Object.setPrototypeOf(this, SSEError.prototype);
  }
}

/**
 * Error thrown when the client is not properly configured.
 */
export class ConfigurationError extends Error {
  readonly name = "ConfigurationError";

  constructor(message: string) {
    super(message);
    Object.setPrototypeOf(this, ConfigurationError.prototype);
  }
}
