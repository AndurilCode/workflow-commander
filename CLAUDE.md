# Claude AI Instructions

## Task Execution Guidelines

### When to Use Workflow Tools
- **Simple tasks**: Handle directly without tools (e.g., basic calculations, straightforward code edits, simple explanations)
- **Complex tasks**: Always use `init_workflow_guidance` for multi-step problems, tasks requiring coordination across files, or when explicit planning would help

### Workflow Execution Process
1. **Initialize**: When using `init_workflow_guidance`, carefully read the returned instructions and follow them precisely
2. **Follow guidance**: Execute all instructions from tools ending with "_guidance" exactly as specified
3. **Stay synchronized**: The workflow state file is your source of truth - keep it current throughout the process

### Tooling
1. **Context7**: Use context7 tool when you need more info about latest documentation about specific technologies(for instance: python, node, typescript). Try to search when required.
2. **GitHub**: Read files from other repositories using GitHub tools, when required.

### Key Principles
- The response from workflow guidance tools contains your execution plan - treat it as authoritative
- Don't skip steps or improvise when following workflow instructions
- If uncertain whether a task is "simple," err on the side of using the workflow tool
