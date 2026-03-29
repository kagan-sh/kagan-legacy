import { Navigate, useParams, useSearchParams, type RouteObject } from 'react-router';
import App from '@/app';
import { RouteError } from '@/components/shared/route-error';

function HydrateFallback() {
  return null;
}

/** Redirect legacy /session/:taskId?lane=X to /task/:taskId?lane=X */
function SessionRedirect() {
  const { taskId } = useParams<{ taskId: string }>();
  const [searchParams] = useSearchParams();
  const lane = searchParams.get('lane');
  const target = `/task/${taskId}${lane ? `?lane=${lane}` : ''}`;
  return <Navigate to={target} replace />;
}

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <App />,
    HydrateFallback,
    errorElement: <RouteError />,
    children: [
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
            index: true,
            element: <Navigate to="/welcome" replace />,
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
            path: 'session/:taskId',
            element: <SessionRedirect />,
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
