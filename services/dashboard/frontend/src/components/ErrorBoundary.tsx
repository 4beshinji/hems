import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  showDetails: boolean;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, showDetails: false };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleDismiss = () => {
    this.setState({ hasError: false, error: null, showDetails: false });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen bg-[var(--gray-50)] flex items-center justify-center p-6">
        <div className="max-w-md w-full bg-white rounded-xl shadow-lg p-8 text-center space-y-6">
          <div className="text-6xl">!</div>
          <h1 className="text-2xl font-bold text-[var(--gray-900)]">
            予期しないエラーが発生しました
          </h1>
          <p className="text-[var(--gray-600)]">
            ダッシュボードの表示中に問題が発生しました。ページを再読み込みしてください。
          </p>

          <div className="flex gap-3 justify-center">
            <button
              onClick={this.handleReload}
              className="px-6 py-2.5 bg-[var(--primary-500)] text-white font-medium rounded-lg hover:bg-[var(--primary-700)] transition-colors"
            >
              再読み込み
            </button>
            <button
              onClick={this.handleDismiss}
              className="px-6 py-2.5 bg-[var(--gray-100)] text-[var(--gray-700)] font-medium rounded-lg hover:bg-[var(--gray-200)] transition-colors"
            >
              復旧を試す
            </button>
          </div>

          {this.state.error && (
            <div className="text-left">
              <button
                onClick={() => this.setState(s => ({ showDetails: !s.showDetails }))}
                className="text-sm text-[var(--gray-500)] hover:text-[var(--gray-700)] transition-colors"
              >
                {this.state.showDetails ? '詳細を隠す' : '詳細を表示'}
              </button>
              {this.state.showDetails && (
                <pre className="mt-2 p-3 bg-[var(--gray-100)] rounded-lg text-xs text-[var(--error-700)] overflow-auto max-h-40">
                  {this.state.error.message}
                  {'\n\n'}
                  {this.state.error.stack}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }
}
