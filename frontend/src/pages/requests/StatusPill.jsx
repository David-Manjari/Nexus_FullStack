import { STATUS_LABELS } from "../../mock/requestsData";

export default function StatusPill({ status }) {
  return <span className={`rq-pill rq-pill--${status}`}>{STATUS_LABELS[status] ?? status}</span>;
}
