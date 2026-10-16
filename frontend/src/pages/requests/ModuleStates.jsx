export function LoadingState({ text = "Loading..." }) {
  return <div className="rq-state" role="status">{text}</div>;
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="rq-state rq-state--error" role="alert">
      <p>{message}</p>
      {onRetry && <button className="rq-btn rq-btn--ghost" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function EmptyState({ text, children }) {
  return (
    <div className="rq-state">
      <p>{text}</p>
      {children}
    </div>
  );
}
