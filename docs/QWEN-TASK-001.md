# QWEN-TASK-001: Simple test task for local agent

## Goal
Create a simple test to verify that the local agent is working correctly

## Files to read
- agent-backend/agents/base_plate_v0.py

## Files to modify
- agent-backend/agents/base_plate_v0.py

## Relevant excerpt
The file is already quite large, so I'll include just the relevant part:
```python
def _validate_design_spec(spec):
    p = spec.parameters
    errors: list[str] = []
    if p.length <= 0:
        errors.append("length must be positive")
    if p.width <= 0:
        errors.append("width must be positive")
    if p.thickness <= 0:
        errors.append("thickness must be positive")
```

## Acceptance test
```powershell
cd C:\projects\sw-copilot\agent-backend
.\.venv\Scripts\python -m pytest tests/test_base_plate_v0.py -q
```

## Success criteria
- Test should pass
- No existing test should regress
- No file outside "Files to modify" is touched

## Forbidden
- Do not touch sw-addin-client/
- Do not modify schemas.py
- Do not install dependencies