# Product Overview

Kortix is an open-source platform for building, managing, and deploying AI agents. The platform includes Suna, a flagship generalist AI worker that demonstrates the full capabilities of the system.

## Core Capabilities

- **Agent Development**: Build custom AI agents with specialized tools, workflows, and knowledge bases
- **Browser Automation**: Navigate websites, extract data, fill forms, automate web workflows
- **File Management**: Create, edit, and organize documents, spreadsheets, presentations, and code
- **Web Intelligence**: Crawling, search capabilities, data extraction and synthesis
- **System Operations**: Command-line execution, system administration, DevOps tasks
- **API Integrations**: Connect with external services via MCP (Model Context Protocol), Composio, and custom integrations

## Use Cases

- Research & analysis (web research, document analysis, data synthesis)
- Customer service automation (support tickets, FAQ responses, onboarding)
- Content creation (marketing copy, documentation, educational materials)
- Sales & marketing (lead qualification, CRM management, outreach campaigns)
- Industry-specific agents (healthcare, finance, legal, education)

## Architecture

The platform consists of four main components:
1. **Backend API** (Python/FastAPI) - Agent orchestration, LLM integration, tool system
2. **Frontend Dashboard** (Next.js/React) - Agent management interface, chat UI, workflow builders
3. **Agent Runtime** (Docker) - Isolated execution environments with browser automation and code interpreter
4. **Database & Storage** (Supabase) - Authentication, agent configs, conversation history, file storage

## License

Apache License 2.0
