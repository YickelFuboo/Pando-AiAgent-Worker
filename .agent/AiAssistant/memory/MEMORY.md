# Agent Memory - Windows System Operations & Project Analysis

## Agent Identity

### Name
- **中文名**：潘多
- **英文名**：Pando

### Core Positioning
- Actively search internet for tools, skills, and resources to accomplish user goals
- Be proactive and resourceful in finding solutions
- Store credentials securely in skill-specific config files

### Response Language
- Use Chinese (中文) to report results when user prefers it

## Project Analysis Workflow

### .pando Directory Structure Standard
For any project analysis, create a standardized `.pando` directory structure:
```
.pando/
├── Functions/
│   ├── 功能1.md
│   ├── 功能2.md
│   └── ...
├── interface.md
├── design.md
└── code.md
```

### Analysis Methodology
1. **Bottom-up Analysis**: Start from smallest subdirectories, then analyze parent directories
2. **Function Documentation**: Each function gets its own md file with:
   - 功能简介
   - 功能规格  
   - 功能约束
   - 主要交互流程
   - 异常分支流程
3. **Layered Documentation**: Root directory contains overall project analysis, subdirectories contain module-specific analysis

## Windows File Operations

### Directory Creation
- Use `mkdir` command to create directories and subdirectories
- Create nested structures step by step to ensure success
- Create `.pando/Functions` subdirectory before adding function files

### File Writing for Chinese Content
- UTF-8 encoding is supported for Chinese characters
- Use `write_file` for structured documentation generation

## Python Projects Analysis Pattern

### Common Directory Structure
```
project_root/
├── app/               # Main application code
│   ├── agents/        # AI agent implementations
│   ├── chat/          # Chat functionality
│   ├── llms/          # Language model integrations
│   ├── session/       # Session management
│   ├── tools/         # Tool implementations
│   └── main.py        # FastAPI application entry
├── config.toml        # Configuration file
├── requirements.txt   # Python dependencies
└── run.py            # Application runner
```

### Analysis Content Guidelines
1. **Functions/** - Document each major functionality as separate markdown files
2. **interface.md** - Document all public APIs and interfaces
3. **design.md** - Document architecture, tech stack, and key design decisions
4. **code.md** - Document coding patterns, style guidelines, and conventions

## Key Technology Patterns Identified

### FastAPI-based Services
- Main entry: `app/main.py` with FastAPI instance
- CORS middleware configuration
- Modular API registration (llm_api, session_api, chat_api, etc.)
- Lifespan management with `@asynccontextmanager`

### Agent Architecture
- BaseAgent abstract class with core functionality
- Multiple agent types: ClineAgent, SWEAgent
- State management: IDLE, RUNNING, COMPLETED, ERROR
- WebSocket integration for real-time communication
- Tool calling framework with XML-style parsing

### LLM Integration
- Factory pattern for multiple LLM providers
- OpenAI-compatible API support (DeepSeek, etc.)
- Token management and streaming support
- Prompt template system

### Session Management
- Session-based conversation handling
- Message history persistence
 Parent-child session relationships

## Windows Command Limitations & Workarounds

### Command Compatibility
- **`head` is NOT available** in Windows CMD
- Use `more` for paging or PowerShell `Select-Object -First N`

### Chinese Character Support
- Chinese characters work in `findstr` patterns
- System descriptions in `wmic` may display garbled Chinese text
- This does not affect functionality - drive letters and numeric values display correctly

## Effective Windows Commands

### Directory Operations
- **List directories only**: `dir <path> /B /A:D`
- **List files with pattern**: `dir <path>\<pattern> /B /S 2>nul`

### Avoid These Patterns
- PowerShell recursive searches with `-Recurse` trigger safety guard blocks

## ClawHub Skill Registry

### Purpose
- Public skill registry at https://clawhub.ai
- Search and install agent skills using natural language

### Commands
- **Search**: `npx --yes clawhub@latest search "<query>" --limit N`
- **Install**: `npx --yes clawhub@latest install <skill_name> --workdir "<path>"`

## Cron Skill (Built-in)

### Modes
1. **Reminder** - direct message to user
2. **Task (agent mode)** - agent executes task and sends result
3. **One-time** - runs once then auto-deletes

### Usage
```python
cron(action="add", message="Reminder text", every_seconds=1200)
cron(action="add", kind="agent", message="Task...", cron_expr="0 7 * * *", tz="Asia/Shanghai")
```

## SendClaw Email Service

### Registration Constraints
- **Handle format**: lowercase letters, numbers, and underscores ONLY (no hyphens!)
- API endpoint: `POST https://sendclaw.com/api/bots/register`

### Windows Compatibility
- `curl` may fail with "path not found" error
- Workaround: write JSON to file first, then use `curl -d @filename`

## Memory Storage Locations

- **Agent-level**: `AiAssistant/memory/MEMORY.md` (permanent)
- **Workspace-specific**: `<workspace_id>/AiAssistant/memory/MEMORY.md`
- **Skill installation**: `<workdir>/skills/<skill_name>/`
