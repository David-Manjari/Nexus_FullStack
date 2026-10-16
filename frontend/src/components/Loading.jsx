import "./StateMessages.css";

export default function Loading({ message = "Loading..." }) {
  return (
    <div className="state-box" role="status" aria-live="polite">
      <span className="state-spinner" aria-hidden="true" />
      <p>{message}</p>
    </div>
  );
}