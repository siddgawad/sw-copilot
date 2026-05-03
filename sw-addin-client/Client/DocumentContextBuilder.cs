using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace SwCopilotAddin.Client
{
    public sealed class DocumentContext
    {
        public string       DocumentType      { get; set; } = "None";
        public int          BodyCount         { get; set; }
        public string       FilePath          { get; set; } = string.Empty;
        public List<string> SelectedEntityIds { get; set; } = new();
    }

    public sealed class DocumentContextBuilder
    {
        private readonly ISldWorks _swApp;

        public DocumentContextBuilder(ISldWorks swApp) => _swApp = swApp;

        public DocumentContext Build()
        {
            var ctx = new DocumentContext();

            IModelDoc2 doc = _swApp.IActiveDoc2;
            if (doc == null) return ctx;

            ctx.FilePath     = doc.GetPathName();
            ctx.DocumentType = ((swDocumentTypes_e)doc.GetType()) switch
            {
                swDocumentTypes_e.swDocPART     => "Part",
                swDocumentTypes_e.swDocASSEMBLY => "Assembly",
                swDocumentTypes_e.swDocDRAWING  => "Drawing",
                _                               => "Unknown",
            };

            if (doc is IPartDoc part)
            {
                var bodies = part.GetBodies2((int)swBodyType_e.swSolidBody, true) as object[];
                ctx.BodyCount = bodies?.Length ?? 0;
            }

            ISelectionMgr selMgr   = doc.ISelectionManager;
            int           selCount = selMgr.GetSelectedObjectCount2(-1);
            for (int i = 1; i <= selCount; i++)
            {
                int typeId = selMgr.GetSelectedObjectType3(i, -1);
                ctx.SelectedEntityIds.Add($"type:{typeId}:index:{i}");
            }

            return ctx;
        }
    }
}
