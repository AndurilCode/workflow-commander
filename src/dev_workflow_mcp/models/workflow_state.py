"""Workflow state models and enums."""

import uuid
from datetime import datetime
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator


class WorkflowPhase(str, Enum):
    """Workflow phases."""

    INIT = "INIT"
    ANALYZE = "ANALYZE"
    BLUEPRINT = "BLUEPRINT"
    CONSTRUCT = "CONSTRUCT"
    VALIDATE = "VALIDATE"


class WorkflowStatus(str, Enum):
    """Workflow status values."""

    READY = "READY"
    RUNNING = "RUNNING"
    NEEDS_PLAN_APPROVAL = "NEEDS_PLAN_APPROVAL"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class WorkflowItem(BaseModel):
    """Individual workflow item."""

    id: int
    description: str
    status: str = "pending"


class WorkflowState(BaseModel):
    """Complete workflow state with client-session support."""

    # Session identification
    client_id: str = Field(default="default", description="Client session identifier")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique session identifier")
    created_at: datetime = Field(default_factory=datetime.now, description="Session creation time")
    
    # Workflow state
    last_updated: datetime = Field(default_factory=datetime.now)
    phase: WorkflowPhase
    status: WorkflowStatus
    current_item: str | None = None
    plan: str = ""
    items: list[WorkflowItem] = Field(default_factory=list)
    log: str = ""
    archive_log: str = ""

    # Template for markdown generation
    MARKDOWN_TEMPLATE: ClassVar[str] = """# Workflow State
_Last updated: {timestamp}_

## State
Phase: {phase}  
Status: {status}  
CurrentItem: {current_item}  

## Plan
{plan}

## Rules
> **Keep every major section under an explicit H2 (`##`) heading so the agent can locate them unambiguously.**

### [PHASE: ANALYZE]
1. Read **project_config.md**, relevant code & docs.  
2. Summarize requirements. *No code or planning.*

### [PHASE: BLUEPRINT]
1. Decompose task into ordered steps.  
2. Write pseudocode or file-level diff outline under **## Plan**.  
3. Set `Status = NEEDS_PLAN_APPROVAL` and await user confirmation.

### [PHASE: CONSTRUCT]
1. Follow the approved **## Plan** exactly.  
2. After each atomic change:  
   - run test / linter commands specified in `project_config.md`  
   - capture tool output in **## Log**  
3. On success of all steps, set `Phase = VALIDATE`.

### [PHASE: VALIDATE]
1. Rerun full test suite & any E2E checks.  
2. If clean, set `Status = COMPLETED`.  
3. Trigger **RULE_ITERATE_01** when applicable.

---

### RULE_INIT_01
Trigger ▶ `Phase == INIT`  
Action ▶ Ask user for first high-level task → `Phase = ANALYZE, Status = RUNNING`.

### RULE_ITERATE_01
Trigger ▶ `Status == COMPLETED && Items contains unprocessed rows`  
Action ▶  
1. Set `CurrentItem` to next unprocessed row in **## Items**.  
2. Clear **## Log**, reset `Phase = ANALYZE, Status = READY`.

### RULE_LOG_ROTATE_01
Trigger ▶ `length(## Log) > 5 000 chars`  
Action ▶ Summarise the top 5 findings from **## Log** into **## ArchiveLog**, then clear **## Log**.

### RULE_SUMMARY_01
Trigger ▶ `Phase == VALIDATE && Status == COMPLETED`  
Action ▶ 
1. Read `project_config.md`.
2. Construct the new changelog line: `- <One-sentence summary of completed work>`.
3. Find the `## Changelog` heading in `project_config.md`.
4. Insert the new changelog line immediately after the `## Changelog` heading and its following newline (making it the new first item in the list).

---

## Items
{items_table}

## Log
{log}

## ArchiveLog
{archive_log}
"""

    @field_validator('client_id')
    @classmethod
    def validate_client_id(cls, v):
        """Validate client_id format."""
        if not v or not isinstance(v, str):
            return "default"
        # Basic validation - alphanumeric plus hyphens and underscores
        if not all(c.isalnum() or c in '-_' for c in v):
            return "default"
        return v

    def add_log_entry(self, entry: str) -> None:
        """Add entry to log with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")  # noqa: DTZ005
        self.log += f"\n[{timestamp}] {entry}"

        # Check if log rotation is needed (>5000 chars)
        if len(self.log) > 5000:
            self.rotate_log()

    def rotate_log(self) -> None:
        """Rotate log to archive when it gets too long."""
        # Move current log to archive
        if self.archive_log:
            self.archive_log += "\n\n--- LOG ROTATION ---\n\n"
        self.archive_log += self.log
        self.log = ""

    def get_next_pending_item(self) -> WorkflowItem | None:
        """Get the next pending item."""
        for item in self.items:
            if item.status == "pending":
                return item
        return None

    def mark_item_completed(self, item_id: int) -> bool:
        """Mark an item as completed."""
        for item in self.items:
            if item.id == item_id:
                item.status = "completed"
                return True
        return False

    def to_markdown(self) -> str:
        """Generate markdown representation of workflow state."""
        # Format timestamp
        timestamp = self.last_updated.strftime("%Y-%m-%d")
        
        # Format current item
        current_item = self.current_item or "null"
        
        # Format items table
        if self.items:
            items_lines = ["| id | description | status |", "|----|-------------|--------|"]
            for item in self.items:
                items_lines.append(f"| {item.id} | {item.description} | {item.status} |")
            items_table = "\n".join(items_lines)
        else:
            items_table = "| id | description | status |\n|----|-------------|--------|\n<!-- No items yet -->"
        
        # Format plan
        plan = self.plan if self.plan.strip() else "<!-- The AI fills this in during the BLUEPRINT phase -->"
        
        # Format log
        log = self.log if self.log.strip() else "<!-- AI appends detailed reasoning, tool output, and errors here -->"
        
        # Format archive log
        archive_log = self.archive_log if self.archive_log.strip() else "<!-- RULE_LOG_ROTATE_01 stores condensed summaries here -->"
        
        return self.MARKDOWN_TEMPLATE.format(
            timestamp=timestamp,
            phase=self.phase.value,
            status=self.status.value,
            current_item=current_item,
            plan=plan,
            items_table=items_table,
            log=log,
            archive_log=archive_log
        )

    @classmethod
    def from_markdown(cls, content: str, client_id: str) -> "WorkflowState":
        """Create WorkflowState from markdown content."""
        # This is a simplified parser - in production you'd want more robust parsing
        lines = content.split('\n')
        
        # Default values
        phase = WorkflowPhase.INIT
        status = WorkflowStatus.READY
        current_item = None
        plan = ""
        log = ""
        archive_log = ""
        items = []
        
        # Parse the markdown (basic implementation)
        current_section = None
        section_content = []
        
        for line in lines:
            if line.startswith('## '):
                # Process previous section
                if current_section and section_content:
                    content_text = '\n'.join(section_content).strip()
                    
                    if current_section == 'Plan':
                        plan = content_text
                    elif current_section == 'Log':
                        log = content_text
                    elif current_section == 'ArchiveLog':
                        archive_log = content_text
                    elif current_section == 'Items':
                        # Parse items table (simplified)
                        items = cls._parse_items_table(section_content)
                
                # Start new section
                current_section = line[3:].strip()
                section_content = []
                
            elif line.startswith('Phase: '):
                phase = WorkflowPhase(line[7:].strip())
            elif line.startswith('Status: '):
                status = WorkflowStatus(line[8:].strip())
            elif line.startswith('CurrentItem: '):
                current_item_text = line[13:].strip()
                current_item = current_item_text if current_item_text != "null" else None
            else:
                if current_section:
                    section_content.append(line)
        
        # Process final section
        if current_section and section_content:
            content_text = '\n'.join(section_content).strip()
            
            if current_section == 'Plan':
                plan = content_text
            elif current_section == 'Log':
                log = content_text
            elif current_section == 'ArchiveLog':
                archive_log = content_text
            elif current_section == 'Items':
                items = cls._parse_items_table(section_content)
        
        return cls(
            client_id=client_id,
            phase=phase,
            status=status,
            current_item=current_item,
            plan=plan,
            items=items,
            log=log,
            archive_log=archive_log
        )

    @classmethod
    def _parse_items_table(cls, lines: list[str]) -> list[WorkflowItem]:
        """Parse items table from markdown lines."""
        items = []
        
        for line in lines:
            if line.startswith('| ') and not line.startswith('|-'):
                parts = [part.strip() for part in line.split('|')[1:-1]]  # Remove empty first/last
                if len(parts) >= 3 and parts[0] != 'id':  # Skip header
                    try:
                        item_id = int(parts[0])
                        description = parts[1]
                        status = parts[2]
                        items.append(WorkflowItem(id=item_id, description=description, status=status))
                    except (ValueError, IndexError):
                        continue  # Skip malformed lines
        
        return items
