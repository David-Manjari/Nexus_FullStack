import { useEffect, useState } from "react";
import {
  addProjectMilestone,
  createProject,
  getProjectDetails,
  getProjectApprovers,
  getProjectAssignableUsers,
  getProjects,
  submitProject,
  updateProjectMilestone,
  updateProjectStatus,
  updateProjectTeam,
} from "../../api/projects";
import { useAuth } from "../../auth/AuthContext";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";
import "./Projects.css";

const STATUS_TRANSITIONS = {
  approved: ["active", "cancelled"],
  active: ["on_hold", "completed", "cancelled"],
  on_hold: ["active", "completed", "cancelled"],
};

function ProjectCard({ project, user, assignableUsers, assignableUsersLoading, onProjectChanged }) {
  const [expanded, setExpanded] = useState(false);
  const [details, setDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [error, setError] = useState("");
  const [nextStatus, setNextStatus] = useState("");
  const [reason, setReason] = useState("");
  const [milestone, setMilestone] = useState({ title: "", description: "", dueDate: "" });
  const [team, setTeam] = useState({ managerId: "", staffIds: [] });
  const [staffToAdd, setStaffToAdd] = useState("");
  const [activeForm, setActiveForm] = useState("");
  const [saving, setSaving] = useState(false);

  const isAssignedProjectManager = project.managerId === user?.id;
  const canChangeStatus = isAssignedProjectManager || ["admin", "manager"].includes(user?.role);
  const isClosed = ["completed", "cancelled"].includes(project.status);
  const canManageTeam = ["admin", "manager"].includes(user?.role) && !isClosed;
  const canManageMilestones =
    (isAssignedProjectManager || ["admin", "manager"].includes(user?.role)) && !isClosed;
  const statusOptions = STATUS_TRANSITIONS[project.status] ?? [];
  const unassignedStaff = assignableUsers.filter(
    (member) => member.role === "staff" && !team.staffIds.includes(member.id)
  );

  async function refreshDetails() {
    setError("");
    const data = await getProjectDetails(project.id);
    setDetails(data);
    setTeam({
      managerId: data.project.managerId == null ? "" : String(data.project.managerId),
      staffIds: data.staff.map((member) => member.id),
    });
    onProjectChanged();
  }

  async function loadDetails() {
    setLoadingDetails(true);
    setError("");
    try {
      const data = await getProjectDetails(project.id);
      setDetails(data);
      setTeam({
        managerId: data.project.managerId == null ? "" : String(data.project.managerId),
        staffIds: data.staff.map((member) => member.id),
      });
    } catch (loadError) {
      setError(loadError.message || "Could not load project details.");
    } finally {
      setLoadingDetails(false);
    }
  }

  async function toggleDetails() {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (!details) await loadDetails();
  }

  async function handleStatusSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await updateProjectStatus(project.id, nextStatus, reason);
      setNextStatus("");
      setReason("");
      await refreshDetails();
      setActiveForm("");
    } catch (saveError) {
      setError(saveError.message || "Could not update project status.");
    } finally {
      setSaving(false);
    }
  }

  async function handleMilestoneSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await addProjectMilestone(project.id, milestone);
      setMilestone({ title: "", description: "", dueDate: "" });
      await refreshDetails();
      setActiveForm("");
    } catch (saveError) {
      setError(saveError.message || "Could not add milestone.");
    } finally {
      setSaving(false);
    }
  }

  async function handleMilestoneStatusChange(milestoneId, status) {
    setSaving(true);
    setError("");
    try {
      await updateProjectMilestone(project.id, milestoneId, status);
      await refreshDetails();
    } catch (saveError) {
      setError(saveError.message || "Could not update milestone.");
    } finally {
      setSaving(false);
    }
  }

  async function handleTeamSubmit(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await updateProjectTeam(project.id, {
        manager_id: team.managerId ? Number(team.managerId) : null,
        staff_ids: staffToAdd
          ? [...team.staffIds, Number(staffToAdd)]
          : team.staffIds,
      });
      setStaffToAdd("");
      await refreshDetails();
      setActiveForm("");
    } catch (saveError) {
      setError(saveError.message || "Could not update project team.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="project-item">
      <div className="project-item__summary">
        <div>
          <div className="project-item_image-wrap"><img src={project.image || "/images/inventory.jpg"} alt={project.name} className="project-item_image" /><h2>{project.name}</h2></div>
          <p className="project-item__meta">
            Project manager: {project.managerName || "Unassigned"}
            <span className={`project-status project-status--${project.status}`}>
              {project.status.replaceAll("_", " ")}
            </span>
          </p>
          {project.description && <p>{project.description}</p>}
          <small>{project.startDate || "No start date"} – {project.endDate || "No end date"}</small>
        </div>
        <button type="button" onClick={toggleDetails} aria-expanded={expanded}>
          {expanded ? "Hide details" : "Manage project"}
        </button>
      </div>

      {expanded && (
        <div className="project-item__details">
          {error && <ErrorMessage message={error} onRetry={loadDetails} />}
          {loadingDetails && <Loading message="Loading project details..." />}
          {details && (
            <>
              <div className="project-actions" aria-label={`Actions for ${project.name}`}>
                {canManageTeam && (
                  <button
                    type="button"
                    aria-expanded={activeForm === "team"}
                    aria-controls={activeForm === "team" ? `team-form-${project.id}` : undefined}
                    onClick={() => setActiveForm(activeForm === "team" ? "" : "team")}
                  >
                    Edit project team
                  </button>
                )}
                {canManageMilestones && (
                  <button
                    type="button"
                    aria-expanded={activeForm === "milestone"}
                    aria-controls={activeForm === "milestone" ? `milestone-form-${project.id}` : undefined}
                    onClick={() => setActiveForm(activeForm === "milestone" ? "" : "milestone")}
                  >
                    Add milestone
                  </button>
                )}
                {canChangeStatus && statusOptions.length > 0 && (
                  <button
                    type="button"
                    aria-expanded={activeForm === "status"}
                    aria-controls={activeForm === "status" ? `status-form-${project.id}` : undefined}
                    onClick={() => setActiveForm(activeForm === "status" ? "" : "status")}
                  >
                    Update status
                  </button>
                )}
              </div>

              <section className="project-section" aria-labelledby={`team-${project.id}`}>
                <h3 id={`team-${project.id}`}>Project team</h3>
                <p>Project manager: {details.project.managerName || "Unassigned"}</p>
                <p>
                  Assigned staff: {details.staff.length
                    ? details.staff.map((member) => member.name).join(", ")
                    : "None"}
                </p>
                {canManageTeam && activeForm === "team" && (
                  <form
                    id={`team-form-${project.id}`}
                    className="project-form"
                    onSubmit={handleTeamSubmit}
                  >
                    <label>
                      Project manager
                      <select
                        value={team.managerId}
                        disabled={saving}
                        onChange={(event) => setTeam({ ...team, managerId: event.target.value })}
                      >
                        <option value="">Unassigned</option>
                        {assignableUsers.filter((member) => member.role !== "store_manager").map((member) => (
                          <option key={member.id} value={member.id}>{member.name} ({member.role})</option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Assign staff
                      <select
                        value={staffToAdd}
                        disabled={saving || assignableUsersLoading || unassignedStaff.length === 0}
                        onChange={(event) => setStaffToAdd(event.target.value)}
                      >
                        <option value="">
                          {assignableUsersLoading
                            ? "Loading staff..."
                            : unassignedStaff.length
                              ? "Select staff"
                              : "No unassigned staff available"}
                        </option>
                        {unassignedStaff.map((member) => (
                          <option key={member.id} value={member.id}>{member.name}</option>
                        ))}
                      </select>
                    </label>
                    <button type="submit" disabled={saving}>
                      {saving ? "Saving..." : "Save project team"}
                    </button>
                  </form>
                )}
              </section>

              <section className="project-section" aria-labelledby={`approval-history-${project.id}`}>
                <h3 id={`approval-history-${project.id}`}>Approval chain history</h3>
                {details.approvalChain.length === 0 ? (
                  <p>This project has not been submitted for approval.</p>
                ) : (
                  <ol className="project-approval-chain">
                    {details.approvalChain.map((entry) => (
                      <li key={entry.id}>
                        <div>
                          <strong>Round {entry.roundNumber}, step {entry.stepOrder}: {entry.approverName}</strong>
                          <span className={`project-status project-status--${entry.status}`}>
                            {entry.status.replaceAll("_", " ")}
                          </span>
                          {entry.comments && <p>{entry.comments}</p>}
                        </div>
                        {entry.decidedAt && <small>{new Date(entry.decidedAt).toLocaleString()}</small>}
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section className="project-section" aria-labelledby={`milestones-${project.id}`}>
                <h3 id={`milestones-${project.id}`}>Milestones</h3>
                {details.milestones.length === 0 ? (
                  <p>No milestones yet.</p>
                ) : (
                  <ul className="milestone-list">
                    {details.milestones.map((item) => (
                      <li key={item.id} className="milestone-item">
                        <div>
                          <strong>{item.title}</strong>
                          {item.description && <p>{item.description}</p>}
                          <small>
                            Due {item.dueDate || "date not set"}
                            {item.completedAt ? ` · Completed ${new Date(item.completedAt).toLocaleDateString()}` : ""}
                          </small>
                        </div>
                        {canManageMilestones ? (
                          <label>
                            Status
                            <select
                              value={item.status}
                              disabled={saving}
                              onChange={(event) => handleMilestoneStatusChange(item.id, event.target.value)}
                            >
                              <option value="planned">Planned</option>
                              <option value="in_progress">In progress</option>
                              <option value="completed">Completed</option>
                            </select>
                          </label>
                        ) : (
                          <span className="milestone-status">{item.status.replaceAll("_", " ")}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}

                {canManageMilestones && activeForm === "milestone" && (
                  <form
                    id={`milestone-form-${project.id}`}
                    className="project-form"
                    onSubmit={handleMilestoneSubmit}
                  >
                    <h4>Add milestone</h4>
                    <label>
                      Title
                      <input
                        required
                        value={milestone.title}
                        onChange={(event) => setMilestone({ ...milestone, title: event.target.value })}
                      />
                    </label>
                    <label>
                      Description
                      <textarea
                        value={milestone.description}
                        onChange={(event) => setMilestone({ ...milestone, description: event.target.value })}
                      />
                    </label>
                    <label>
                      Due date
                      <input
                        type="date"
                        value={milestone.dueDate}
                        onChange={(event) => setMilestone({ ...milestone, dueDate: event.target.value })}
                      />
                    </label>
                    <button type="submit" disabled={saving}>{saving ? "Saving..." : "Add milestone"}</button>
                  </form>
                )}
              </section>

              <section className="project-section" aria-labelledby={`history-${project.id}`}>
                <h3 id={`history-${project.id}`}>Status audit</h3>
                {details.statusHistory.length === 0 ? (
                  <p>No status changes recorded.</p>
                ) : (
                  <ol className="project-history">
                    {details.statusHistory.map((entry) => (
                      <li key={entry.id}>
                        <strong>
                          {entry.fromStatus ? `${entry.fromStatus.replaceAll("_", " ")} to ` : "Created as "}
                          {entry.toStatus.replaceAll("_", " ")}
                        </strong>
                        {entry.reason && <p>{entry.reason}</p>}
                        <small>
                          {entry.changedByName || "Unknown user"}
                          {entry.changedAt ? ` · ${new Date(entry.changedAt).toLocaleString()}` : ""}
                        </small>
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              {canChangeStatus && statusOptions.length > 0 && activeForm === "status" && (
                <form
                  id={`status-form-${project.id}`}
                  className="project-form project-form--status"
                  onSubmit={handleStatusSubmit}
                >
                  <h3>Update project status</h3>
                  <label>
                    New status
                    <select required value={nextStatus} onChange={(event) => setNextStatus(event.target.value)}>
                      <option value="">Select a status</option>
                      {statusOptions.map((status) => (
                        <option key={status} value={status}>
                          {project.status === "draft" && status === "approved"
                            ? "Accepted"
                            : status.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Update note
                    <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
                  </label>
                  <button type="submit" disabled={saving || !nextStatus}>
                    {saving ? "Saving..." : "Save status update"}
                  </button>
                </form>
              )}
            </>
          )}
        </div>
      )}
    </li>
  );
}

export default function ProjectsPage() {
  const { user } = useAuth();
  const [projects, setProjects] = useState([]);
  const [assignableUsers, setAssignableUsers] = useState([]);
  const [assignableUsersLoading, setAssignableUsersLoading] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [submitForApproval, setSubmitForApproval] = useState(false);
  const [approvers, setApprovers] = useState([]);
  const [approversLoading, setApproversLoading] = useState(false);
  const [approversError, setApproversError] = useState("");
  const [approverLoadAttempt, setApproverLoadAttempt] = useState(0);
  const [approverChain, setApproverChain] = useState([]);
  const [nextApproverId, setNextApproverId] = useState("");
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

  useEffect(() => {
    if (!["admin", "manager"].includes(user?.role)) {
      setAssignableUsersLoading(false);
      return;
    }

    let active = true;
    setAssignableUsersLoading(true);
    getProjectAssignableUsers()
      .then((users) => {
        if (active) setAssignableUsers(users);
      })
      .catch((loadError) => {
        if (active) setError(loadError.message || "Could not load assignable users.");
      })
      .finally(() => {
        if (active) setAssignableUsersLoading(false);
      });

    return () => { active = false; };
  }, [user?.role]);

  useEffect(() => {
    if (!showCreateForm || !submitForApproval) return undefined;

    let active = true;
    setApproversLoading(true);
    setApproversError("");
    getProjectApprovers()
      .then((users) => {
        if (active) setApprovers(users);
      })
      .catch((loadError) => {
        if (active) setApproversError(loadError.message || "Could not load project approvers.");
      })
      .finally(() => {
        if (active) setApproversLoading(false);
      });

    return () => { active = false; };
  }, [showCreateForm, submitForApproval, approverLoadAttempt]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (
      submitForApproval
      && (approversLoading || approversError || approverChain.length === 0)
    ) {
      return;
    }
    setSaving(true);
    setError("");
    try {
      const createdProject = await createProject(form);
      let approvalError = "";
      if (submitForApproval) {
        try {
          await submitProject(createdProject.id, approverChain.map(Number));
        } catch (submitError) {
          approvalError = submitError.message || "Approval submission failed.";
        }
      }
      setForm({ name: "", description: "", startDate: "", endDate: "" });
      setSubmitForApproval(false);
      setApproverChain([]);
      setNextApproverId("");
      setShowCreateForm(false);
      await load();
      if (approvalError) {
        setError(
          `"${createdProject.name}" was created as a draft, but could not be submitted for approval: ${approvalError}`
        );
      }
    } catch (saveError) {
      setError(saveError.message || "Could not create project.");
    } finally {
      setSaving(false);
    }
  }

  function closeCreateForm() {
    setShowCreateForm(false);
    setSubmitForApproval(false);
    setApproverChain([]);
    setNextApproverId("");
  }

  return (
    <section className="projects-page">
      <header className="project-page-header">
        <h1>Projects</h1>
        <button
          type="button"
          aria-expanded={showCreateForm}
          aria-controls={showCreateForm ? "project-create-form" : undefined}
          onClick={() => showCreateForm ? closeCreateForm() : setShowCreateForm(true)}
        >
          {showCreateForm ? "Close project form" : "Create project"}
        </button>
      </header>
      {error && <ErrorMessage message={error} onRetry={load} />}
      {showCreateForm && (
        <form id="project-create-form" className="project-create-form" onSubmit={handleSubmit}>
          <h2>Create project</h2>
          <label>
            Project name
            <input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          </label>
          <label>
            Description
            <textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
          </label>
          <div className="project-date-fields">
            <label>
              Start date
              <input type="date" value={form.startDate} onChange={(event) => setForm({ ...form, startDate: event.target.value })} />
            </label>
            <label>
              End date
              <input type="date" value={form.endDate} onChange={(event) => setForm({ ...form, endDate: event.target.value })} />
            </label>
          </div>
          <section className="project-create-approval" aria-label="Optional project approval">
            <label className="project-create-approval__toggle">
              <input
                type="checkbox"
                checked={submitForApproval}
                disabled={saving}
                onChange={(event) => {
                  setSubmitForApproval(event.target.checked);
                  if (!event.target.checked) {
                    setApproverChain([]);
                    setNextApproverId("");
                  }
                }}
              />
              Submit for approval after creating this project
            </label>
            {submitForApproval && (
              <div className="project-form">
                <h3>Approval chain</h3>
                <p>Select active managers or admins in the order they should review the project.</p>
                {approversError && (
                  <ErrorMessage
                    message={approversError}
                    onRetry={() => setApproverLoadAttempt((attempt) => attempt + 1)}
                  />
                )}
                {approversLoading ? (
                  <Loading message="Loading approvers..." />
                ) : !approversError && (
                  <>
                    <label>
                      Next approver
                      <select
                        value={nextApproverId}
                        disabled={saving || approvers.length === approverChain.length}
                        onChange={(event) => setNextApproverId(event.target.value)}
                      >
                        <option value="">
                          {approvers.length ? "Select an approver" : "No other active approvers available"}
                        </option>
                        {approvers
                          .filter((approver) => !approverChain.includes(String(approver.id)))
                          .map((approver) => (
                            <option key={approver.id} value={approver.id}>
                              {approver.name} ({approver.role})
                            </option>
                          ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      disabled={saving || !nextApproverId}
                      onClick={() => {
                        setApproverChain([...approverChain, nextApproverId]);
                        setNextApproverId("");
                      }}
                    >
                      Add approver to chain
                    </button>
                    {approverChain.length > 0 && (
                      <ol className="project-approval-chain">
                        {approverChain.map((approverId, index) => {
                          const approver = approvers.find(
                            (candidate) => String(candidate.id) === approverId
                          );
                          return (
                            <li key={approverId}>
                              <span>{approver?.name || "Approver"} — step {index + 1}</span>
                              <button
                                type="button"
                                disabled={saving}
                                onClick={() => setApproverChain(
                                  approverChain.filter((id) => id !== approverId)
                                )}
                              >
                                Remove
                              </button>
                            </li>
                          );
                        })}
                      </ol>
                    )}
                  </>
                )}
              </div>
            )}
          </section>
          <div className="project-actions">
            <button
              type="submit"
              disabled={saving || (
                submitForApproval
                && (approversLoading || approversError || approverChain.length === 0)
              )}
            >
              {saving
                ? submitForApproval ? "Creating and submitting..." : "Creating..."
                : "Create project"}
            </button>
            <button type="button" disabled={saving} onClick={closeCreateForm}>Cancel</button>
          </div>
        </form>
      )}

      <section aria-labelledby="projects-list-heading">
        <h2 id="projects-list-heading">Projects you can access</h2>
        {loading && <Loading message="Loading projects..." />}
        {!loading && projects.length === 0 && (
          <EmptyState title="No projects" message="Projects you create or manage will appear here." />
        )}
        {!loading && projects.length > 0 && (
          <ul className="projects-list">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                user={user}
                assignableUsers={assignableUsers}
                assignableUsersLoading={assignableUsersLoading}
                onProjectChanged={load}
              />
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}