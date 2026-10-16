import { apiRequest } from "./http";

export async function getUsers() {
  // Use the admin-only account endpoint so inventory assignment and admin views share real users.
  const { accounts } = await apiRequest("/users/accounts");
  return accounts.map((account) => ({
    id: account.user_id,
    name: account.username,
    email: account.email,
    role: account.role,
    active: account.is_active,
  }));
}

export async function getAssignableUsers() {
  // Store managers use a separate route because the backend limits asset assignment by role.
  const { users } = await apiRequest("/users/assignable");
  return users.map((user) => ({
    id: user.user_id,
    name: user.username,
    role: user.role,
  }));
}

export async function createUser(fields) {
  return apiRequest("/users/accounts", { method: "POST", body: fields });
}

export async function updateUser(id, changes) {
  return apiRequest(`/users/accounts/${id}`, { method: "PATCH", body: changes });
}

export async function deactivateUser(id) {
  return apiRequest(`/users/accounts/${id}`, { method: "DELETE" });
}