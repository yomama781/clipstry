export const StatusBadge = ({ status, testId }) => {
  const map = {
    verified: { label: "VERIFIED", color: "#10B981" },
    pending: { label: "PENDING", color: "#F59E0B" },
    failed: { label: "FAILED", color: "#EF4444" },
    active: { label: "ACTIVE", color: "#002FA7" },
    ended: { label: "ENDED", color: "#52525B" },
  };
  const m = map[status] || { label: status.toUpperCase(), color: "#09090B" };
  return (
    <span
      data-testid={testId}
      className="brut-badge"
      style={{ color: m.color, backgroundColor: `${m.color}15` }}
    >
      <span
        className="inline-block w-1.5 h-1.5"
        style={{ backgroundColor: m.color }}
      />
      {m.label}
    </span>
  );
};
