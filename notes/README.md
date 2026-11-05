# Working notes

This directory holds the working notes of the project: analysis of the earlier repositories,
design decisions, implementation plans, test logs and hard-won technical facts. They were written
during development, partly together with an AI assistant, and they are kept so that the next
maintainer (human or assistant) can see why things are the way they are.

They are not user documentation. The user documentation is the README at the repository root,
which does not link here on purpose. Nothing in this directory is needed to use the system.

| File | Content |
|---|---|
| `00-host-setup.md` | management host requirements per OS, with the reasons |
| `01-repository-map.md` | which upstream repositories and branches matter |
| `02-existing-ansible-analysis.md` | how the upstream playbooks provisioned a robot before this project |
| `03-provisioning-steps-mapping.md` | where every provisioning step landed in the roles |
| `04-software-firmware-versioning.md` | versioning, firmware options, monitoring signals |
| `05-implementation-plan.md` | decisions, target layout, milestones |
| `06-v1-reproduce-current-setup.md` | the legacy host-ROS path and its test log |
| `07-container-runtime.md` | workspaces, images, CI, monitoring hooks, runbook, the main test log |
| `08-hardware-test-guide.md` | manual verification steps, known issues 1 to 10, troubleshooting table |
| `10-monitoring.md` | node_exporter, Prometheus, Grafana, the dashboard, alert rules |
| `semaphore-setup.md` | what the Semaphore bootstrap creates, Linux host specifics, task fields |
| `workspaces.md` | the full rules for workspace files and generated workspaces |
| `student-image.md` | the planned student image (not built) |
