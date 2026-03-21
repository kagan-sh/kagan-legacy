import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  level?: 'page' | 'feature' | 'widget';
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error boundary caught:', error, errorInfo);
  }

  private reset = () => this.setState({ hasError: false, error: null });

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      const { level = 'page' } = this.props;
      const message = this.state.error?.message ?? 'An unexpected error occurred';

      if (level === 'widget') {
        return (
          <span className="text-sm text-destructive">
            {message}{' '}
            <button
              type="button"
              onClick={this.reset}
              className="underline underline-offset-2 hover:text-destructive/80"
            >
              Retry
            </button>
          </span>
        );
      }

      if (level === 'feature') {
        return (
          <Alert variant="destructive">
            <AlertCircle className="size-4" />
            <AlertTitle>Something went wrong</AlertTitle>
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        );
      }

      // page (default)
      return (
        <div className="flex flex-col items-center justify-center gap-4 p-8 text-center">
          <Alert variant="destructive" className="max-w-md">
            <AlertCircle className="size-4" />
            <AlertTitle>Something went wrong</AlertTitle>
            <AlertDescription>{message}</AlertDescription>
          </Alert>
          <Button onClick={this.reset}>Try again</Button>
        </div>
      );
    }
    return this.props.children;
  }
}
