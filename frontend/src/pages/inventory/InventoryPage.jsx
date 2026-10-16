import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { getItems, retireItem, returnItem } from "../../api/inventory";
import { getAssignableUsers } from "../../api/users";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";
import StatusBadge from "./StatusBadge";
import ItemFormModal from "./ItemFormModal";
import AssignModal from "./AssignModal";
import HistoryModal from "./HistoryModal";
import "./InventoryPage.css";

const STATUSES = ["all", "available", "assigned", "maintenance"];

export default function InventoryPage({ type }) {
  const { user } = useAuth();
  const canManage = user?.role === "store_manager";
  const [items, setItems] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [category, setCategory] = useState("all");
  const [reloadKey, setReloadKey] = useState(0);
  const [modal, setModal] = useState(null);

  useEffect(() => {
    setSearch("");
    setStatus("all");
    setCategory("all");
  }, [type]);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      setLoading(true);
      setError(null);
      try {
        setItems(await getItems(type, { signal: controller.signal }));
      } catch (err) {
        if (err.name !== "AbortError") setError(err.message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    load();
    return () => controller.abort();
  }, [type, reloadKey]);

  useEffect(() => {
    if (canManage) getAssignableUsers().then(setUsers).catch(() => setUsers([]));
  }, [canManage]);

  const reload = () => setReloadKey((k) => k + 1);
  const closeModal = () => setModal(null);
  const openAdd = () => setModal({ kind: "form", item: null });
  const saved = () => {
    closeModal();
    reload();
  };

  async function runAction(action) {
    setActionError(null);
    try {
      await action();
      reload();
    } catch (err) {
      setActionError(err.message);
    }
  }

  const userName = (id) => users.find((u) => u.id === id)?.name ?? "Unknown user";
  const categories = ["all", ...new Set(items.map((i) => i.category))];

  const visible = items.filter((item) => {
    const q = search.toLowerCase();
    const matchesSearch = item.name.toLowerCase().includes(q) || item.sku.toLowerCase().includes(q);
    const matchesStatus = status === "all" || item.status === status;
    const matchesCategory = category === "all" || item.category === category;
    return matchesSearch && matchesStatus && matchesCategory;
  });

  return (
    <section className="inventory">
      <nav className="inventory-tabs">
        <NavLink to="/inventory/tools">Tools</NavLink>
        <NavLink to="/inventory/devices">Devices</NavLink>
        <NavLink to="/inventory/vehicles">Vehicles</NavLink>
      </nav>

      <div className="inventory-toolbar">
        <input
          type="search"
          placeholder="Search by name or SKU"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s === "all" ? "All statuses" : s}</option>
          ))}
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          {categories.map((c) => (
            <option key={c} value={c}>{c === "all" ? "All categories" : c}</option>
          ))}
        </select>
        {canManage && <button onClick={openAdd}>Add {type}</button>}
      </div>

      {actionError && <ErrorMessage message={actionError} />}
      {loading && <Loading message="Loading inventory..." />}
      {error && <ErrorMessage message={`Something went wrong: ${error}`} onRetry={reload} />}
      {!loading && !error && visible.length === 0 && (
        <EmptyState
          title="No items found"
          message="Try a different search or filter, or add a new item."
          actionLabel={canManage ? `Add ${type}` : undefined}
          onAction={canManage ? openAdd : undefined}
        />
      )}

      {!loading && !error && visible.length > 0 && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th></th>
                <th>Name</th>
                <th>Category</th>
                <th>SKU</th>
                <th>Status</th>
                <th>Assigned to</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id}>
                  <td>
                    {item.image && <img className="item-thumb" src={item.image} alt="" loading="lazy" />}
                  </td>
                  <td>{item.name}</td>
                  <td>{item.category}</td>
                  <td>{item.sku}</td>
                  <td><StatusBadge status={item.status} /></td>
                  <td>{item.assignedTo ? userName(item.assignedTo) : "-"}</td>
                  <td className="row-actions">
                    {canManage && item.status === "available" && (
                      <button onClick={() => setModal({ kind: "assign", item })}>Assign</button>
                    )}
                    {canManage && item.status === "assigned" && (
                      <button onClick={() => runAction(() => returnItem(item.id, item.assignmentId))}>Return</button>
                    )}
                    <button onClick={() => setModal({ kind: "history", item })}>History</button>
                    {canManage && <button onClick={() => setModal({ kind: "form", item })}>Edit</button>}
                    {canManage && <button
                      disabled={item.status === "assigned" || item.status === "retired"}
                      onClick={() => {
                        if (window.confirm(`Retire ${item.name}?`)) runAction(() => retireItem(item.id));
                      }}
                    >
                      Retire
                    </button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {canManage && modal?.kind === "form" && (
        <ItemFormModal
          type={type}
          item={modal.item}
          existingItems={items}
          onClose={closeModal}
          onSaved={saved}
        />
      )}
      {canManage && modal?.kind === "assign" && (
        <AssignModal item={modal.item} users={users} onClose={closeModal} onSaved={saved} />
      )}
      {modal?.kind === "history" && (
        <HistoryModal item={modal.item} users={users} onClose={closeModal} />
      )}
    </section>
  );
}