import { type ReactNode } from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { Provider } from 'jotai';
import { createStore } from 'jotai';
import { MemoryRouter } from 'react-router';
import { TooltipProvider } from '@/components/ui/tooltip';

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  store?: ReturnType<typeof createStore>;
  initialEntries?: string[];
}

export function renderWithProviders(
  ui: ReactNode,
  { store = createStore(), initialEntries = ['/'], ...options }: CustomRenderOptions = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <TooltipProvider>
          <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
        </TooltipProvider>
      </Provider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...options }),
    store,
  };
}
