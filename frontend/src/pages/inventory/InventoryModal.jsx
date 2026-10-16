export default function InventoryModal({ title, onClose, children }) {
  return (
    <div className="inv-overlay" onClick={onClose}>
      <div
        className="inv-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}