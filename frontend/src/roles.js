export const ROLES = {
  ADMIN: "admin",
  MANAGER: "manager",
  STORE_MANAGER: "store_manager",
  STAFF: "staff",
};

export const ROLE_DEFINITIONS = [
  {
    key: ROLES.ADMIN,
    label: "Admin",
    description: "Full access to system configuration and all user administration tools.",
    permissions: ["manage_users", "manage_roles", "approve_requests", "view_finance"],
  },
  {
    key: ROLES.MANAGER,
    label: "Manager",
    description: "Can manage operational workflows and review approvals for their team.",
    permissions: ["approve_requests", "review_reports", "assign_tasks"],
  },
  {
    key: ROLES.STORE_MANAGER,
    label: "Store manager",
    description: "Can manage inventory, assign assets, and handle returns.",
    permissions: ["view_inventory", "manage_inventory", "assign_assets"],
  },
  {
    key: ROLES.STAFF,
    label: "Staff",
    description: "Access to routine operational workflows and self-service requests.",
    permissions: ["submit_requests", "view_dashboard"],
  },
];

export function getRoleLabel(role) {
  const match = ROLE_DEFINITIONS.find((entry) => entry.key === role);
  return match ? match.label : role;
}

export function hasAnyRole(user, allowedRoles = []) {
  if (!user) return false;
  const userRoles = Array.isArray(user.roles) ? user.roles : [user.role];
  return allowedRoles.some((role) => userRoles.includes(role));
}
