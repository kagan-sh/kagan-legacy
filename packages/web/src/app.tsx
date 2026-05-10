import { Provider } from 'jotai';
import { TooltipProvider } from '@/components/ui/tooltip';
import { useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router';
import { useAtomValue, useSetAtom } from 'jotai';
import { Toaster } from 'sonner';
import { isAuthenticatedAtom, isAuthLoadingAtom, hydrateAuthAtom } from '@/lib/atoms/auth';
import { resolvedThemeAtom, initThemeAtom } from '@/lib/atoms/theme';
import { store } from '@/lib/atoms/store';
import { Spinner } from '@/components/ui/spinner';
import { registerBuiltinCommands } from '@/lib/commands/commands';

function AppShell() {
  const isAuthenticated = useAtomValue(isAuthenticatedAtom);
  const isLoading = useAtomValue(isAuthLoadingAtom);
  const resolvedTheme = useAtomValue(resolvedThemeAtom);
  const hydrateAuth = useSetAtom(hydrateAuthAtom);
  const initTheme = useSetAtom(initThemeAtom);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    registerBuiltinCommands();
    initTheme();
    hydrateAuth();
  }, [hydrateAuth, initTheme]);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark');
  }, [resolvedTheme]);

  useEffect(() => {
    if (isLoading) return;
    const publicPaths = ['/welcome'];
    if (!isAuthenticated && !publicPaths.some((p) => location.pathname.startsWith(p))) {
      navigate('/welcome', { replace: true });
    }
  }, [isAuthenticated, isLoading, location.pathname, navigate]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--background)]">
        <Spinner className="size-8 text-[var(--muted-foreground)]" />
      </div>
    );
  }

  return (
    <>
      <Outlet />
      <Toaster
        theme={resolvedTheme}
        position="bottom-right"
        toastOptions={{
          style: {
            background: 'var(--card)',
            color: 'var(--card-foreground)',
            border: '1px solid var(--border)',
          },
        }}
      />
    </>
  );
}

export default function App() {
  return (
    <Provider store={store}>
      <TooltipProvider>
        <AppShell />
      </TooltipProvider>
    </Provider>
  );
}
