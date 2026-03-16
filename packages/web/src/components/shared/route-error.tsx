import { useRouteError, isRouteErrorResponse, useNavigate } from 'react-router';
import { AlertCircle, RefreshCw, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';

export function RouteError() {
  const error = useRouteError();
  const navigate = useNavigate();

  const isChunkError =
    error instanceof Error &&
    (error.message.includes('dynamically imported module') ||
      error.message.includes('Failed to fetch'));

  const title = isRouteErrorResponse(error)
    ? `${error.status} — ${error.statusText}`
    : isChunkError
      ? 'Page failed to load'
      : 'Something went wrong';

  const message = isChunkError
    ? 'A new version may have been deployed. Reload to get the latest.'
    : isRouteErrorResponse(error)
      ? error.data?.message ?? 'The page you requested could not be found.'
      : error instanceof Error
        ? error.message
        : 'An unexpected error occurred.';

  const handleReload = () => {
    window.location.reload();
  };

  return (
    <div className="flex h-full min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center">
      <Alert variant="destructive" className="max-w-md">
        <AlertCircle className="size-4" />
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>{message}</AlertDescription>
      </Alert>
      <div className="flex gap-3 pt-2">
        <Button variant="outline" onClick={() => navigate(-1)}>
          <ArrowLeft className="size-4" />
          Go back
        </Button>
        <Button onClick={handleReload}>
          <RefreshCw className="size-4" />
          Reload
        </Button>
      </div>
    </div>
  );
}
