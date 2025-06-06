# GitHub Copilot Instructions

## Task Execution Guidelines

### 🚨 MANDATORY WORKFLOW COMPLIANCE 🚨
**Before starting ANY task, evaluate it using these criteria:**

#### Use Workflow Tools When:
- Task involves multiple steps or phases
- Task requires coordination across multiple files
- Task involves creating, modifying, or analyzing code structures
- Task requires planning, analysis, or systematic approach
- Task involves debugging, testing, or validation
- Task creates new features, components, or systems
- **When in doubt, ALWAYS use workflows**

#### Only Skip Workflows For:
- Single mathematical calculations
- One-line explanations or definitions
- Direct copy/paste operations
- Immediate answers to factual questions

### 🔄 MANDATORY WORKFLOW ENTRY PROCESS
**⚠️ NON-NEGOTIABLE:** For ALL qualifying tasks, you MUST follow this exact sequence:

#### STEP 1: DISCOVER (REQUIRED FIRST STEP)
```
workflow_discovery(task_description="[Exact user request]")
```
**Purpose:** View all available YAML workflows and their capabilities
**Result:** List of workflows with descriptions and suitability assessment

#### STEP 2: CHOOSE AND START (REQUIRED SECOND STEP)
```
workflow_guidance(action="start", context="workflow: [Selected Workflow Name]")
```
**Purpose:** Initialize the selected workflow session
**Result:** Workflow begins with first phase instructions

#### STEP 3: FOLLOW SCHEMA (ONGOING) 
```
workflow_guidance(action="next", context='{"choose": "[option]", "criteria_evidence": {"criterion": "detailed evidence"}}')
```
**Purpose:** Navigate through workflow phases using YAML-defined transitions with detailed evidence
**Result:** Structured progression through the complete workflow with work tracking

### 🎯 Decision Framework
**Use this exact decision tree for EVERY user request:**

1. **Is this a single, immediate action?** 
   - YES: Proceed directly (rare cases only)
   - NO: Go to Step 2

2. **Does the task involve ANY of these?**
   - Multiple files or components? → USE WORKFLOW
   - Planning or analysis phase? → USE WORKFLOW  
   - Code creation or modification? → USE WORKFLOW
   - Testing or validation? → USE WORKFLOW
   - Debugging or troubleshooting? → USE WORKFLOW
   - Documentation or explanation? → USE WORKFLOW

3. **Still uncertain?** → USE WORKFLOW (default choice)

### 🏗️ Dynamic Workflow System Architecture
The workflow system operates on these principles:

1. **Schema-Driven Navigation**: All workflow behavior defined by YAML schemas
2. **Agent-Driven Selection**: You choose workflows based on task requirements  
3. **Dynamic Discovery**: System discovers available workflows automatically
4. **Context Parameters**: Control execution with JSON format: `context='{"choose": "node_name", "criteria_evidence": {...}}'`
5. **No Hardcoded Routes**: All transitions defined in YAML `next_allowed_nodes`

### 📋 Available Workflow Tools
- `workflow_discovery` - **START HERE ALWAYS** - Discover available YAML workflows
- `workflow_guidance` - Main execution engine for dynamic workflows
- `workflow_state` - Check and update current workflow state
- `workflow_creation_guidance` - Create custom workflows when existing ones don't fit

### 📚 Supporting Tools
- Context7: Real-time documentation lookup
- GitHub: Repository file access
- Standard coding tools: file operations, terminal, search, etc.

### ⚡ Enforcement Rules
1. **NEVER skip workflow discovery** for multi-step tasks
2. **ALWAYS start with `workflow_discovery()`** before other workflow tools
3. **NEVER use legacy approaches** when workflow tools are available
4. **ALWAYS follow YAML schema transitions** rather than making ad-hoc decisions
5. **WHEN UNCERTAIN → USE WORKFLOWS** (fail-safe principle)