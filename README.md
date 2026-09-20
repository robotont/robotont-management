# Robotont Management

Centralized management and monitoring for Robotont robots.

Initial scope:
- Provision Robotont computers using Ansible
- Update Robotont ROS software
- Update Robotont firmware
- Provide a simple management interface using Semaphore
- Monitor Robotont health using Prometheus and Grafana

Planned architecture:
- Ansible for configuration and deployment
- Semaphore as the management UI
- Prometheus for metrics collection
- Grafana for monitoring
- Docker Compose for management-server services

Future work may include:
- Automated Ubuntu installation
- Containerized Robotont runtime
- More advanced inventory management
- VPN / overlay networking
- Centralized logging
