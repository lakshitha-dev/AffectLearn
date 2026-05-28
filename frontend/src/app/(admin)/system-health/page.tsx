export default function SystemHealthPage() {
  const services = [
    { name: "API Server", status: "operational", latency: "42ms", uptime: "99.98%" },
    { name: "Affect Detection Agent", status: "operational", latency: "180ms", uptime: "99.91%" },
    { name: "Content Adapter Agent", status: "operational", latency: "95ms", uptime: "99.95%" },
    { name: "WebSocket Gateway", status: "operational", latency: "8ms", uptime: "99.99%" },
    { name: "Database (PostgreSQL)", status: "operational", latency: "12ms", uptime: "100%" },
    { name: "Webcam Feature Processor", status: "degraded", latency: "380ms", uptime: "98.2%" },
  ];

  const STATUS_STYLES: Record<string, { dot: string; label: string; text: string }> = {
    operational: { dot: "bg-green-500", label: "Operational", text: "text-green-600" },
    degraded: { dot: "bg-amber-500 animate-pulse", label: "Degraded", text: "text-amber-600" },
    down: { dot: "bg-red-500 animate-pulse", label: "Down", text: "text-red-600" },
  };

  const operational = services.filter((s) => s.status === "operational").length;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">System Health</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Real-time status of all platform services
        </p>
      </div>

      <div className="mb-6 flex items-center gap-3 rounded-lg border px-5 py-4 border-green-200 bg-green-50 dark:border-green-800/40 dark:bg-green-900/10">
        <span className="h-2.5 w-2.5 rounded-full bg-green-500" />
        <div>
          <p className="text-sm font-semibold text-green-800 dark:text-green-400">
            {operational}/{services.length} services operational
          </p>
          <p className="text-xs text-green-700 dark:text-green-500">
            Minor degradation in webcam feature processing — behavioral mode unaffected
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Service</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">Latency</th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">30-day Uptime</th>
            </tr>
          </thead>
          <tbody>
            {services.map((svc) => {
              const s = STATUS_STYLES[svc.status];
              return (
                <tr key={svc.name} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-medium text-foreground">{svc.name}</td>
                  <td className="px-4 py-3">
                    <span className={`flex items-center gap-2 text-sm font-medium ${s.text}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
                      {s.label}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{svc.latency}</td>
                  <td className="px-4 py-3 text-muted-foreground">{svc.uptime}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
