import { useEffect, useState } from "react";
import { createProject, getProjects } from "../../api/projects";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";

export default function ProjectsPage() {
  const [projects, setProjects] = useState([]);
  const [form, setForm] = useState({ name: "", description: "", startDate: "", endDate: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setProjects(await getProjects());
    } catch (loadError) {
      setError(loadError.message || "Could not load projects.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      // This page uses the existing backend project API instead of leaving the nav link unimplemented.
      await createProject(form);
      setForm({ name: "", description: "", startDate: "", endDate: "" });
      await load();
    } catch (saveError) {
      setError(saveError.message || "Could not create project.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <h1>Projects</h1>
      {error && <ErrorMessage message={error} onRetry={load} />}
      <form onSubmit={handleSubmit} style={{ display: "grid", gap: 12, maxWidth: 640, marginBottom: 24 }}>
        <label>Project name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label>Description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
        <div style={{ display: "flex", gap: 12 }}>
          <label>Start date<input type="date" value={form.startDate} onChange={(event) => setForm({ ...form, startDate: event.target.value })} /></label>
          <label>End date<input type="date" value={form.endDate} onChange={(event) => setForm({ ...form, endDate: event.target.value })} /></label>
        </div>
        <button type="submit" disabled={saving}>{saving ? "Creating..." : "Create project"}</button>
      </form>
      {loading && <Loading message="Loading projects..." />}
      {!loading && projects.length === 0 && <EmptyState title="No projects" message="Projects you create or can access will appear here." />}
      {!loading && projects.length > 0 && (
        <ul style={{ display: "grid", gap: 12, padding: 0, listStyle: "none" }}>
          {projects.map((project) => (
            <li key={project.id} style={{ border: "1px solid #d1d5db", padding: 16 }}>
              <strong>{project.name}</strong> <span>{project.status}</span>
              {project.description && <p>{project.description}</p>}
              <small>{project.startDate || "No start date"} – {project.endDate || "No end date"}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}