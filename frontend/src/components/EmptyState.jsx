import "./StateMessages.css";

export default function EmptyState({
  title = "Nothing here yet",
  message,
  actionLabel,
  onAction,
}) {
  return (
    <div className="state-box">
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {actionLabel && onAction && (
        <button type="button" className="state-button" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}