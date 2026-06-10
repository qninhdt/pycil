export default function AdminHome() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
      <p className="text-sm text-muted-foreground">
        Pick a section from the sidebar. Users, Reports, Metrics, Flags, Health,
        and Audit land here as later phases ship.
      </p>
    </div>
  );
}
