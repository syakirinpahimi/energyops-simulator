import { redirect } from "next/navigation";

// The audit log lives at /audit-log (matches the backend /audit-log
// route and the user spec). /audit is kept as a permanent redirect for
// older bookmarks and an earlier draft of the API contract.
export default function AuditRedirect() {
  redirect("/audit-log");
}
