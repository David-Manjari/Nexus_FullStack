import { apiRequest } from "./http";

function mapProject(project) {
  return {
    id: project.project_id,
    name: project.name,
    description: project.description ?? "",
    status: project.status,
    startDate: project.start_date,
    endDate: project.end_date,
    createdAt: project.created_at,
  };
}

export async function getProjects() {
  const { projects } = await apiRequest("/projects");
  return projects.map(mapProject);
}

export async function createProject(fields) {
  const { project } = await apiRequest("/projects", {
    method: "POST",
    body: {
      name: fields.name,
      description: fields.description,
      start_date: fields.startDate || null,
      end_date: fields.endDate || null,
    },
  });
  return mapProject(project);
}