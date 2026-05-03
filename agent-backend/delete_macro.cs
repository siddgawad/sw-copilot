using System;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

public class Macro
{
    public static void Run(SolidWorks.Interop.sldworks.ISldWorks swApp)
    {
        IModelDoc2 doc = (IModelDoc2)swApp.ActiveDoc;
        if (doc == null)
        {
            Console.WriteLine("No active document.");
            return;
        }

        var deletable = new List<Feature>();
        Feature feat = (Feature)doc.FirstFeature();
        while (feat != null)
        {
            Feature next = (Feature)feat.GetNextFeature();
            string typeName = feat.GetTypeName2() ?? "";

            if (typeName != "RefPlane" &&
                typeName != "OriginProfileFeature" &&
                typeName != "Reference" &&
                typeName != "HistoryFolder" &&
                typeName != "SelectionSetFolder" &&
                typeName != "SensorFolder" &&
                typeName != "MaterialFolder" &&
                typeName != "CommentsFolder" &&
                typeName != "DesignBinder")
            {
                deletable.Add(feat);
            }

            feat = next;
        }

        doc.ClearSelection2(true);
        foreach (Feature item in deletable)
        {
            item.Select2(true, 0);
        }

        int deleted = 0;
        if (deletable.Count > 0)
        {
            int options = (int)swDeleteSelectionOptions_e.swDelete_Absorbed |
                          (int)swDeleteSelectionOptions_e.swDelete_Children;
            if (doc.Extension.DeleteSelection2(options))
            {
                deleted = deletable.Count;
            }
        }

        doc.ClearSelection2(true);
        doc.ForceRebuild3(false);
        Console.WriteLine("Deleted " + deleted + " sketches/features.");
    }
}
