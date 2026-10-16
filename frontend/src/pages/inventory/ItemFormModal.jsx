import { useState } from "react";
import { createItem, updateItem } from "../../api/inventory";
import InventoryModal from "./InventoryModal";

function validate(values, existingItems, editingId, type) {
  const errors = {};
  if (!values.name.trim()) errors.name = "Name is required";
  if (type === "vehicle" && !values.plateNo.trim()) errors.plateNo = "Plate number is required for vehicles";
  if (type === "vehicle" && (!Number.isInteger(Number(values.mileage)) || Number(values.mileage) < 0)) {
    errors.mileage = "Mileage must be a whole number of 0 or more";
  }
  const clash = values.sku.trim() && existingItems.some(
    (i) => i.id !== editingId && i.sku.toLowerCase() === values.sku.trim().toLowerCase()
  );
  if (clash) errors.sku = "This SKU already exists";
  return errors;
}

export default function ItemFormModal({ type, item, existingItems, onClose, onSaved }) {
  const [values, setValues] = useState({
    name: item?.name ?? "",
    category: item?.category ?? "",
    brand: item?.brand ?? "",
    sku: item?.sku ?? "",
    status: item?.status ?? "available",
    plateNo: item?.plateNo ?? "",
    make: item?.make ?? "",
    model: item?.model ?? "",
    mileage: item?.mileage ?? 0,
  });
  const [errors, setErrors] = useState({});
  const [apiError, setApiError] = useState(null);
  const [saving, setSaving] = useState(false);

  const change = (e) => setValues({ ...values, [e.target.name]: e.target.value });

  async function handleSubmit(e) {
    e.preventDefault();
    const found = validate(values, existingItems, item?.id, type);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    setApiError(null);
    const data = {
      name: values.name.trim(),
      category: values.category.trim(),
      brand: values.brand.trim(),
      sku: values.sku.trim(),
      plateNo: values.plateNo.trim(),
      make: values.make.trim(),
      model: values.model.trim(),
      mileage: Number(values.mileage),
    };
    if (item?.status !== "assigned") data.status = values.status;

    try {
      if (item) await updateItem(item.id, data);
      else await createItem(type, data);
      onSaved();
    } catch (err) {
      setApiError(err.message);
      setSaving(false);
    }
  }

  return (
    <InventoryModal title={item ? `Edit ${item.name}` : `Add ${type}`} onClose={onClose}>
      <form className="inv-form" onSubmit={handleSubmit} noValidate>
        <label>
          Name
          <input name="name" value={values.name} onChange={change} />
          {errors.name && <span className="field-error">{errors.name}</span>}
        </label>
        <label>
          Category
          <input name="category" value={values.category} onChange={change} />
        </label>
        <label>
          Brand
          <input name="brand" value={values.brand} onChange={change} />
        </label>
        <label>
          SKU / serial number (optional)
          <input name="sku" value={values.sku} onChange={change} />
          {errors.sku && <span className="field-error">{errors.sku}</span>}
        </label>
        {type === "vehicle" && (
          <>
            <label>
              Plate number
              <input name="plateNo" value={values.plateNo} onChange={change} />
              {errors.plateNo && <span className="field-error">{errors.plateNo}</span>}
            </label>
            <label>
              Make
              <input name="make" value={values.make} onChange={change} />
            </label>
            <label>
              Model
              <input name="model" value={values.model} onChange={change} />
            </label>
            <label>
              Mileage
              <input name="mileage" type="number" min="0" value={values.mileage} onChange={change} />
              {errors.mileage && <span className="field-error">{errors.mileage}</span>}
            </label>
          </>
        )}
        {item?.status !== "assigned" && (
          <label>
            Status
            <select name="status" value={values.status} onChange={change}>
              <option value="available">available</option>
              <option value="maintenance">maintenance</option>
              <option value="retired">retired</option>
            </select>
          </label>
        )}
        {apiError && <p className="inventory-error">{apiError}</p>}
        <div className="inv-form-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={saving}>{saving ? "Saving..." : "Save"}</button>
        </div>
      </form>
    </InventoryModal>
  );
}