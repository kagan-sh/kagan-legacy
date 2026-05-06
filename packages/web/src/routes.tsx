import { Navigate, type RouteObject } from 'react-router';
import App from '@/app';
import { RouteError } from '@/components/shared/route-error';

function HydrateFallback() {
  return null;
}

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <App />,
    HydrateFallback,
    errorElement: <RouteError />,
    children: [
      {
        index: true,
        element: <Navigate to="/welcome" replace />,
        errorElement: <RouteError />,
      },
      {
        path: 'welcome',
        lazy: () => import('@/pages/welcome-page'),
        errorElement: <RouteError />,
      },
      {
        lazy: () => import('@/components/layout/app-layout'),
        errorElement: <RouteError />,
        children: [
          {
            path: 'home',
            element: <Navigate to="/welcome" replace />,
            errorElement: <RouteError />,
          },
          {
            path: 'board',
            lazy: () => import('@/pages/board-page'),
            errorElement: <RouteError />,
          },
          {
            path: 'workspace',
            lazy: () => import('@/pages/workspace-page'),
            errorElement: <RouteError />,
          },
          {
            path: 'task/:id',
            lazy: () => import('@/pages/task-detail-page'),
            errorElement: <RouteError />,
          },
          {
            path: 'chat/:id',
            lazy: () => import('@/pages/chat-page'),
            errorElement: <RouteError />,
          },
          {
            path: 'settings',
            lazy: () => import('@/pages/settings-page'),
            errorElement: <RouteError />,
          },
        ],
      },
    ],
  },
];
