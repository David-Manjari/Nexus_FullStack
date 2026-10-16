import "./StateMessages.css";

export default function ErrorMessage({
  message = "Something went wrong. Please try again.",
  onRetry,
}) {
  return (
    <div className="state-box state-error" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="state-button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}