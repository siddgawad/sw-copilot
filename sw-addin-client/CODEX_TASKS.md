# Codex Task Queue — Smart Impossibility Detection (Layer 7)

## Context

We just added **Layer 1** (Python pattern router) checks that catch impossible geometry
BEFORE the graph reaches the C# executor. These work for deterministic patterns only.

For **LLM-generated graphs**, the C# executor is the last line of defense. The error
messages in `OperationExecutor.cs` have been updated to be actionable — they now suggest
alternatives instead of just saying "failed".

## What's Already Done (don't redo these)

### In `OperationExecutor.cs`:

1. **Counterbore depth vs thickness** (line ~1212): Already checks
   `counterboreDepth >= thicknessMm - 0.01`. Error message now says:
   ```
   ERROR: M6 counterbore depth is 6mm (ISO 4762), but part thickness is only 5mm.
   Try: use simple holes instead ('make 4 M6 holes'), or increase plate thickness to ≥7mm.
   ```

2. **Fillet radius vs thickness** (line ~1127): Already checks
   `radius > (thickness/2) - 0.01`. Error message now says:
   ```
   ERROR: Fillet radius 3mm is too large. Part thickness is 5mm, so maximum fillet radius is 2.5mm.
   Try: 'fillet all edges 2mm'
   ```

3. **Generic fillet failure** (line ~1152): Now suggests a safe radius:
   ```
   ERROR: Fillet failed — some edges are incompatible with R=3mm.
   Part thickness is 5mm. Try: 'fillet all edges 1.5mm'
   ```

## Remaining Codex Tasks (prioritized)

### CX-7 — Fillet Auto-Retry with Reduced Radius

**When `FeatureFillet` returns null** (some edges incompatible), automatically:
1. Clear selection
2. Re-select edges, filtering out edges shorter than 2× radius
3. Retry with same radius
4. If still null, try 60% of max safe radius
5. If success at reduced radius, report: `"Fillet R=1.5mm (reduced from 3mm — some edges incompatible)"`

Location: `ExecFillet()` in `OperationExecutor.cs`, after the `if (fillet == null)` block.

### CX-8 — Chamfer Distance vs Thickness Check

Add to `ExecChamfer()` the same pattern as fillet:
```csharp
if ((op.FeatureIds == null || op.FeatureIds.Length == 0) &&
    TryGetPartThicknessMm(doc, out double thicknessMm))
{
    double maxDistMm = (thicknessMm / 2.0) - 0.01;
    if (maxDistMm > 0.0 && (op.DistanceMm ?? 0.0) > maxDistMm)
    {
        double suggested = Math.Round(maxDistMm * 0.8, 1);
        if (suggested < 0.5) suggested = 0.5;
        return $"ERROR: Chamfer {(op.DistanceMm ?? 0.0):0.###} mm is too large. " +
               $"Part thickness is {thicknessMm:0.###} mm, max safe = {maxDistMm:0.#} mm. " +
               $"Try: 'chamfer all edges {suggested:0.#}mm'";
    }
}
```

### CX-9 — Live Test the Updated Build

After rebuild + re-register, test these exact prompts in SolidWorks:

| # | Prompt Sequence | Expected |
|---|---|---|
| 1 | `create a 100x60x5mm plate` → `make 4 M6 counterbore holes at corners` | Blocked: "counterbore depth 6mm exceeds thickness 5mm" |
| 2 | `create a 100x60x10mm plate` → `make 4 M6 counterbore holes at corners` | ✅ Success |
| 3 | `create a 100x60x5mm plate` → `fillet all edges 3mm` | Blocked: "radius 3mm too large, max 2.5mm" |
| 4 | `create a 100x60x5mm plate` → `fillet all edges 2mm` | ✅ Success |
| 5 | `create a 100x60x5mm plate` → `make 4 M6 holes at corners` → `fillet all edges 2mm` | ✅ Success |

Write results to CLAUDE.md Handoff Queue.

### CX-10 — Edge-Length Filtering in SelectEdgesForFillet

In the "all edges" path of `SelectEdgesForFillet`, after filtering arc edges, also
skip linear edges shorter than the fillet diameter:

```csharp
// After: if (curve != null && !curve.IsLine()) continue;
// Add:
try {
    double edgeLenMm = ((IEdge)edgeObj).GetLength() * 1000.0;
    if (edgeLenMm < (op.RadiusMm ?? 0) * 2.0) continue;
} catch { }
```

This prevents `FeatureFillet` from failing on short edges created by holes.

## Build Command
```powershell
dotnet build SwCopilotAddin.csproj -c Release -p:Platform=x64 -p:RegisterForComInterop=false `
  -p:OutDir=bin\x64\Release-beta2\net48\
```
Must produce: **0 Warning(s), 0 Error(s)**
