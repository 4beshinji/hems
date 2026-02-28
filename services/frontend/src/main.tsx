import React, { lazy, Suspense } from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ErrorBoundary from './components/ErrorBoundary'
import AppLayout from './app/layout'
import LoadingState from './components/shared/LoadingState'
import './index.css'

const DashboardPage = lazy(() => import('./app/dashboard/page'))
const PhysicalPage = lazy(() => import('./app/physical/page'))
const DigitalPage = lazy(() => import('./app/digital/page'))
const UserPage = lazy(() => import('./app/user/page'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 0,
      refetchOnWindowFocus: false,
    },
  },
})

const router = createBrowserRouter([
  {
    element: <AppLayout />,
    errorElement: (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center p-8">
          <h1 className="text-2xl font-bold text-destructive mb-4">Error</h1>
          <p className="text-muted-foreground">ページの読み込みに失敗しました</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-primary text-primary-foreground rounded-lg"
          >
            再読み込み
          </button>
        </div>
      </div>
    ),
    children: [
      {
        index: true,
        element: (
          <Suspense fallback={<LoadingState />}>
            <DashboardPage />
          </Suspense>
        ),
      },
      {
        path: 'physical',
        element: (
          <Suspense fallback={<LoadingState />}>
            <PhysicalPage />
          </Suspense>
        ),
      },
      {
        path: 'digital',
        element: (
          <Suspense fallback={<LoadingState />}>
            <DigitalPage />
          </Suspense>
        ),
      },
      {
        path: 'user',
        element: (
          <Suspense fallback={<LoadingState />}>
            <UserPage />
          </Suspense>
        ),
      },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
