# SolidWorks 2021 COM API Reference

Verified by introspection of the actual interop DLLs. Do not change argument
counts or types — these signatures are load-bearing for `OperationExecutor.cs`.
Only Codex needs this file, and only when touching the executor.

## Sketch

```csharp
sketchMgr.InsertSketch(true)                         // call twice: open, then close
sketchMgr.CreateCornerRectangle(x1,y1,0, x2,y2,0)    // metres
sketchMgr.CreateCircleByRadius(cx,cy,0, radius)      // metres
sketchMgr.CreateLine(x1,y1,0, x2,y2,0)
```

## Sketch dimensions / fully-defined sketches

Verified by interop reflection and SOLIDWORKS API Help:

```csharp
doc.IAddHorizontalDimension2(x, y, z)                 // selected sketch segment / points
doc.IAddVerticalDimension2(x, y, z)                   // selected sketch segment / points
doc.IAddDiameterDimension2(x, y, z)                   // selected circle / arc segment
doc.SketchAddConstraints("sgCOINCIDENT")              // selected sketch point + origin

sketchMgr.FullyDefineSketch(
  true,  true, relationMask,
  true,  1, null,
  1,     null,
  1,     1)
```

`AddDimension2` and the horizontal/vertical/diameter variants create display
dimensions for selected entities. `FullyDefineSketch` can apply relations and
baseline dimensions to the active sketch; the SOLIDWORKS C# help example uses
relation flags for horizontal/vertical plus baseline dimension schemes with
null datums.

Sources:
- https://help.solidworks.com/2016/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDoc2~AddDimension2.html
- https://help.solidworks.com/2013/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.ISketchManager~FullyDefineSketch.html
- https://help.solidworks.com/2021/English/api/sldworksapi/Fully_Define_Underdefined_Sketch_Example_CSharp.htm

## Extrude

```csharp
featMgr.FeatureExtrusion2(true,false,false, endCond,0, depth,0,
  false,false,false,false, 0,0, false,false,false,false,
  true,true,true, 0,0.0,false)

featMgr.FeatureCut3(true,false,false, endCond,swEndCondBlind, depth,0,
  false,false,false,false, 0,0, false,false,false,false,
  false,true,true,true,true,false, 0,0.0,false)
```

## Fillet / Chamfer (return object — must cast to Feature)

```csharp
(Feature)featMgr.FeatureFillet(
  Options, R1, Ftyp, OverflowType,
  Radii_obj[], SetBackDist_obj[], PointRadius_obj[])

(Feature)featMgr.InsertFeatureChamfer(
  Options, ChamferType, Width, Angle,
  OtherDist, VD1, VD2, VD3)
```

## Patterns

```csharp
featMgr.FeatureCircularPattern3(
  Number, Spacing, FlipDirection, DName,
  GeometryPattern, EqualSpacing)                     // 6 params

featMgr.FeatureLinearPattern3(
  Num1,Spacing1, Num2,Spacing2,
  FlipDir1,FlipDir2, DName1,DName2,
  GeomPat, VaryInstance)                             // 10 params

featMgr.InsertMirrorFeature2(
  BMirrorBody, BGeometryPattern,
  BMerge, BKnit, ScopeOptions)                       // 5 params
```

## Revolve (20 params)

```csharp
featMgr.FeatureRevolve2(
  SingleDir, IsSolid, IsThin, IsCut,
  ReverseDir, BothDirUpToSame,
  Dir1Type, Dir2Type, Dir1Angle, Dir2Angle,
  OffsetReverse1, OffsetReverse2,
  OffsetDistance1, OffsetDistance2,
  ThinType, ThinThickness1, ThinThickness2,
  Merge, UseFeatScope, UseAutoSelect)
```

## Body / part queries

`GetBodies2` lives on `IPartDoc`, not `IModelDoc2`:

```csharp
IPartDoc part = doc as IPartDoc;
object[] bodies = part?.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[];
```

## Architecture constraints (load-bearing — never break)

| Constraint | Why |
|---|---|
| `OperationExecutor.Execute()` runs on STA thread | ISldWorks COM is STA-bound; calling from another thread = COM deadlock |
| All SolidWorks COM dimensions in **metres** | Internal unit. The `Mm(double?)` helper converts mm to m throughout the executor |
| `EmbedInteropTypes=false` on SW interop refs | SW loads these from its own dir; embedding breaks COM type identity |
| `_features` dict is per-Execute-call | Cross-request refs (e.g. `f1` from previous turn) fall back to `SelectTopFaceOfBody()` |
