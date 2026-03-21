import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider, createBrowserRouter } from 'react-router';
import { routes } from '@/routes';
import { installVitePreloadRecovery } from '@/lib/utils/vite-preload-recovery';
import '@/app.css';

const router = createBrowserRouter(routes);

installVitePreloadRecovery();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
