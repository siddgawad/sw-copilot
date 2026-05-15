# Codex Task — SW Copilot: Workflow Automation Wedge (Market-Research-Driven Pivot)

> Run from `C:\projects\sw-copilot\`
> `codex --approval-mode full-auto`

## Strategic context (read before coding)

Market research (docs/MARKET_RESEARCH_FINDINGS.md) confirms:
- The commercially proven wedge is WORKFLOW AUTOMATION, not free-form part generation
- MecAgent wins on: macro generation, batch exports, drawing cleanup, repetitive edits
- Engineer communities complain most about: batch exports, title block edits, drawing gaps
- Part generation from natural language is still immature and skepticism-heavy

The existing OperationGraph → COM executor is the RIGHT engine. We just need new
operation types that target workflow pain rather than only part creation.

Read `CLAUDE.md` fully, then `docs/MARKET_RESEARCH_FINDINGS.md`, then implement below.

**Test command:** `cd agent-backend && .venv\Scripts\python -m pytest -q`
**Build command (C#):**
```
cd sw-addin-client
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false "-p:SolidWorksPath=C:\projects\sw-copilot\sw-addin-client\lib\solidworks" --no-restore
```
Baseline: **206 passed, 9 skipped**. Do not break it.

---

## Task 1 — `update_title_block` operation (C# + Python)

**Why:** Title block and custom property updates are one of the top reported time-sinks.
An engineer should be able to type "set revision to C, drawn by John, date today" and have it done instantly.

### Python side — `agent-backend/models/schemas.py`

Add to `OperationDto` (or as a new schema class if you prefer):
```python
class TitleBlockFields(BaseModel):
    revision: str | None = None
    drawn_by: str | None = None
    checked_by: str | None = None
    title: str | None = None
    description: str | None = None
    date: str | None = None          # ISO date string: "2026-05-15"
    custom: dict[str, str] = {}      # any other custom property key → value
```

Add `title_block: TitleBlockFields | None = None` to `OperationDto`.

### C# side — `sw-addin-client/Execution/OperationExecutor.cs`

Add a new operation handler `ExecUpdateTitleBlock(IModelDoc2 doc, OperationDto op)`:

```csharp
private string ExecUpdateTitleBlock(IModelDoc2 doc, OperationDto op)
{
    if (op.TitleBlock == null) return "ERROR: title_block fields required";

    var customProps = (CustomPropertyManager)doc.Extension.get_CustomPropertyManager("");

    var fields = new Dictionary<string, string>();
    if (!string.IsNullOrEmpty(op.TitleBlock.Revision))   fields["Revision"]    = op.TitleBlock.Revision;
    if (!string.IsNullOrEmpty(op.TitleBlock.DrawnBy))    fields["DrawnBy"]     = op.TitleBlock.DrawnBy;
    if (!string.IsNullOrEmpty(op.TitleBlock.CheckedBy))  fields["CheckedBy"]   = op.TitleBlock.CheckedBy;
    if (!string.IsNullOrEmpty(op.TitleBlock.Title))      fields["Description"] = op.TitleBlock.Title;
    if (!string.IsNullOrEmpty(op.TitleBlock.Date))       fields["Date"]        = op.TitleBlock.Date;
    foreach (var kv in op.TitleBlock.Custom ?? new Dictionary<string,string>())
        fields[kv.Key] = kv.Value;

    var updated = new List<string>();
    foreach (var kv in fields)
    {
        customProps.Add(kv.Key, false, (int)swCustomInfoType_e.swCustomInfoText, kv.Value);
        // Add() updates if key already exists when bDeleteExisting=false
        updated.Add($"{kv.Key}={kv.Value}");
    }

    if (updated.Count == 0) return "NOOP: no title block fields provided";
    return $"Title block updated: {string.Join(", ", updated)}";
}
```

Register in `Dispatch()`:
```csharp
case "update_title_block": return ExecUpdateTitleBlock(doc, op);
```

Also add `TitleBlockFields` DTO to `sw-addin-client/Client/OperationGraphDto.cs`:
```csharp
public class TitleBlockFieldsDto
{
    [JsonProperty("revision")]    public string? Revision    { get; set; }
    [JsonProperty("drawn_by")]    public string? DrawnBy     { get; set; }
    [JsonProperty("checked_by")] public string? CheckedBy   { get; set; }
    [JsonProperty("title")]      public string? Title       { get; set; }
    [JsonProperty("date")]       public string? Date        { get; set; }
    [JsonProperty("custom")]     public Dictionary<string, string>? Custom { get; set; }
}
```
Add `[JsonProperty("title_block")] public TitleBlockFieldsDto? TitleBlock { get; set; }` to `OperationDto`.

**Acceptance:** Build passes 0 errors. Add a Python schema test in `tests/test_schema.py`:
```python
def test_title_block_roundtrip():
    op = OperationDto(id="tb1", type="update_title_block",
                      title_block=TitleBlockFields(revision="C", drawn_by="John"))
    assert op.title_block.revision == "C"
```

---

## Task 2 — `export_file` operation (C# + Python)

**Why:** Batch export to PDF/DXF/STEP is the #1 automation request in every engineering community.
"Export all drawings to PDF with today's date in the filename" should be one prompt.

### Python side

Add to `OperationDto`:
```python
class ExportFileOp(BaseModel):
    format: Literal["PDF", "DXF", "STEP", "IGES", "STL"]
    output_path: str | None = None     # absolute path or None for same dir as doc
    filename_template: str | None = None  # e.g. "{title}_{revision}_{date}"
```
Add `export_file: ExportFileOp | None = None` to `OperationDto`.

### C# side

Add `ExecExportFile(IModelDoc2 doc, OperationDto op)`:

```csharp
private string ExecExportFile(IModelDoc2 doc, OperationDto op)
{
    if (op.ExportFile == null) return "ERROR: export_file config required";

    string docPath = doc.GetPathName();
    string dir     = op.ExportFile.OutputPath ?? Path.GetDirectoryName(docPath) ?? "";
    string baseName = BuildExportFilename(doc, op.ExportFile.FilenameTemplate
                       ?? Path.GetFileNameWithoutExtension(docPath));

    string ext = op.ExportFile.Format.ToUpper() switch {
        "PDF"  => ".pdf",
        "DXF"  => ".dxf",
        "STEP" => ".step",
        "IGES" => ".igs",
        "STL"  => ".stl",
        _      => ".pdf"
    };

    string outPath = Path.Combine(dir, baseName + ext);

    int errors = 0, warnings = 0;
    bool ok = doc.Extension.SaveAs3(outPath,
        (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
        (int)swSaveAsOptions_e.swSaveAsOptions_Silent,
        null, null, ref errors, ref warnings);

    if (!ok) return $"ERROR: Export failed (errors={errors} warnings={warnings})";
    return $"Exported to {outPath}";
}

private string BuildExportFilename(IModelDoc2 doc, string template)
{
    var cpm = (CustomPropertyManager)doc.Extension.get_CustomPropertyManager("");
    string Get(string key) {
        string val = "", res = "";
        cpm.Get5(key, false, out val, out res, out _);
        return string.IsNullOrEmpty(res) ? val : res;
    }
    return template
        .Replace("{title}",    Get("Description").Replace(" ", "_"))
        .Replace("{revision}", Get("Revision"))
        .Replace("{date}",     DateTime.Now.ToString("yyyy-MM-dd"))
        .Replace("{docname}",  Path.GetFileNameWithoutExtension(doc.GetPathName() ?? "part"));
}
```

Register:
```csharp
case "export_file": return ExecExportFile(doc, op);
```

**Acceptance:** Build passes 0 errors.

---

## Task 3 — `check_drawing` operation (C# — advisory mode only)

**Why:** Drawing QA is high-value, low-risk. The check is advisory — it reports problems,
never modifies anything. Engineers trust advisory tools faster than autonomous ones.

### C# side

Add `ExecCheckDrawing(IModelDoc2 doc, OperationDto op)`:

```csharp
private string ExecCheckDrawing(IModelDoc2 doc, OperationDto op)
{
    // Only works on drawing documents
    DrawingDoc? drawing = doc as DrawingDoc;
    if (drawing == null) return "ERROR: check_drawing requires an active drawing document";

    var issues = new List<string>();

    // Check 1: title block custom properties present
    var cpm = (CustomPropertyManager)doc.Extension.get_CustomPropertyManager("");
    string[] required = { "Description", "Revision", "DrawnBy" };
    foreach (string key in required)
    {
        string val = "", res = "";
        cpm.Get5(key, false, out val, out res, out _);
        if (string.IsNullOrWhiteSpace(val) && string.IsNullOrWhiteSpace(res))
            issues.Add($"MISSING_PROPERTY: '{key}' is empty");
    }

    // Check 2: sheets have views
    object[] sheets = (object[])drawing.GetSheetNames();
    foreach (object sheetName in sheets ?? Array.Empty<object>())
    {
        drawing.ActivateSheet(sheetName.ToString()!);
        object[]? views = doc.GetDrawingDoc()?.GetViews() as object[];
        if (views == null || views.Length == 0)
            issues.Add($"EMPTY_SHEET: sheet '{sheetName}' has no drawing views");
    }

    // Check 3: no dangling dimensions (dimensions not attached to geometry)
    // Walk all annotations on all sheets
    object[]? annots = doc.Extension.GetAnnotations() as object[];
    int danglingCount = 0;
    if (annots != null)
    {
        foreach (object annotObj in annots)
        {
            Annotation? ann = annotObj as Annotation;
            if (ann == null) continue;
            if (ann.IsDangling()) danglingCount++;
        }
    }
    if (danglingCount > 0)
        issues.Add($"DANGLING_DIMENSIONS: {danglingCount} dimension(s) not attached to geometry");

    if (issues.Count == 0) return "Drawing check PASSED: no issues found";

    return "Drawing check ISSUES:\n" + string.Join("\n", issues.Select(i => "  • " + i));
}
```

Register:
```csharp
case "check_drawing": return ExecCheckDrawing(doc, op);
```

**Acceptance:** Build passes 0 errors. Never modifies the document.

---

## Task 4 — Box and cylinder deterministic fast paths (Python)

**Read:** The research confirms geometry generation is valid as Phase 2 — but only for
highly templateable, machine-verified shapes. Box and cylinder are the right starting point.

Create `agent-backend/agents/box_v0.py`:
Match: "50mm wide 30mm deep 20mm tall box", "100x60x40mm block", "50 by 30 by 20 rectangular block"
Parse: width (X), depth (Y), height (Z). Three numbers without labels → width, depth, height.
Emit OperationGraph schema_version "0.2" with: create_part, create_sketch (Front Plane),
add_center_rectangle (length_mm=width, width_mm=depth), extrude_boss (depth_mm=height), rebuild.

Create `agent-backend/agents/cylinder_v0.py`:
Match: "40mm diameter shaft 100mm long", "cylinder 30mm radius 50mm tall", "30mm circle extruded 60mm"
Parse: diameter OR radius (if "Nmm circle/cylinder" without qualifier → treat as diameter → radius=N/2).
Emit: create_part, create_sketch (Front Plane), add_circle (center 0,0, radius_mm=R), extrude_boss, rebuild.

Wire both into `/generate` in `agent-backend/main.py` before the LLM call.

Write tests in `agent-backend/tests/test_fast_paths.py` — at least 5 matching and 3 non-matching
cases per parser.

**Acceptance:** tests pass; existing 206 tests still pass.

---

## Files FORBIDDEN to modify

- `agent-backend/tests/test_security.py`
- `agent-backend/standards/dimension_resolver.py`
- `.github/workflows/`
- `agent-backend/models/schemas.py` — only ADD new fields, never remove existing ones

## Commit format

One commit per task: `feat(executor): update_title_block operation`
After all tasks: run full test suite and build, then report pass/fail summary.
