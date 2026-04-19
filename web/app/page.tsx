import Link from "next/link";

export default function HomePage() {
  return (
    <div className="panel">
      <h2>Welcome</h2>
      <p>
        Flux turns merchant transaction data into a real-time CFO. Connect a
        merchant on the <Link href="/connect">Connect</Link> tab to start
        ingesting transactions through Knot.
      </p>
      <p className="muted">
        All Knot operations (session creation, sync, webhooks) run on the
        orchestrator. The browser never sees the Knot secret.
      </p>
    </div>
  );
}
