import { STATUS_LABELS } from "../../mock/requestsData";

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function RequestTimeline({ history = [] }) {
  return (
    <ol className="rq-timeline">
      {history.map((entry, index) => (
        <li key={index} className={`rq-timeline__item rq-timeline__item--${entry.status}`}>
          <span className="rq-timeline__dot" aria-hidden="true" />
          <div>
            <strong>{STATUS_LABELS[entry.status] ?? entry.status}</strong>
            <p>{entry.note}</p>
            <small>{entry.by} · {formatDate(entry.at)}</small>
          </div>
        </li>
      ))}
    </ol>
  );
}
