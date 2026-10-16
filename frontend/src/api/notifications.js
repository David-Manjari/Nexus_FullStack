import { apiRequest } from "./http";

function mapNotification(item) {
  return {
    id: item.notification_id,
    userId: item.user_id,
    message: item.message,
    type: item.notif_type,
    read: item.is_read,
    emailSent: item.email_sent,
    createdAt: item.created_at,
  };
}

export async function getNotifications() {
  const { notifications } = await apiRequest("/notifications");
  return notifications.map(mapNotification);
}

export async function getUnreadCount() {
  const notifications = await getNotifications();
  return notifications.filter((item) => !item.read).length;
}

export async function markAsRead(id) {
  const { notification } = await apiRequest(`/notifications/${id}/read`, {
    method: "PATCH",
    body: {},
  });
  return mapNotification(notification);
}

export async function markAllAsRead() {
  await apiRequest("/notifications/read-all", { method: "POST", body: {} });
  return true;
}