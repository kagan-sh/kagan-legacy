import { describe, expect, it } from 'vitest';
import { Navigate, matchRoutes } from 'react-router';
import { routes } from '@/routes';

describe('routes', () => {
  it('redirects the retired analytics surface to workspace', () => {
    const matches = matchRoutes(routes, '/analytics');
    const analyticsRoute = matches?.at(-1)?.route;

    expect(analyticsRoute?.path).toBe('analytics');
    expect(analyticsRoute?.element).toEqual(<Navigate to="/workspace" replace />);
  });
});
