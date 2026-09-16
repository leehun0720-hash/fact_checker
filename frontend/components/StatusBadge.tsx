import { STATUS_LABEL, type JobStatus } from "@/lib/types";

export default function StatusBadge({ status }: { status: JobStatus }) {
  return <span className={`status ${status}`}>{STATUS_LABEL[status] ?? status}</span>;
}
