using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
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
        private static readonly Regex InjectionPattern = new Regex(
            "(RULE:|SYSTEM:|INSTRUCTION:|DEVELOPER:|ASSISTANT:|IGNORE\\s+PREVIOUS|DISREGARD\\s+PREVIOUS|<\\|im_start\\|>|<\\|im_end\\|>)",
            RegexOptions.IgnoreCase | RegexOptions.Compiled);

        public DocumentContextBuilder(ISldWorks swApp) => _swApp = swApp;

        public DocumentContext Build()
        {
            var ctx = new DocumentContext();

            IModelDoc2 doc = _swApp.IActiveDoc2;
            if (doc == null) return ctx;

            ctx.FilePath     = SafeFileName(doc.GetPathName());
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
                ctx.SelectedEntityIds.Add(SanitizeContextValue($"type:{typeId}:index:{i}"));
            }

            return ctx;
        }

        private static string SafeFileName(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
                return string.Empty;

            try
            {
                return SanitizeContextValue(Path.GetFileName(path));
            }
            catch
            {
                return SanitizeContextValue(path);
            }
        }

        private static string SanitizeContextValue(string value)
        {
            if (string.IsNullOrEmpty(value))
                return string.Empty;

            var chars = value.ToCharArray();
            for (int i = 0; i < chars.Length; i++)
            {
                char c = chars[i];
                if (c == '\r' || c == '\n' || c == '`' || char.IsControl(c))
                    chars[i] = ' ';
            }

            string sanitized = new string(chars);
            sanitized = InjectionPattern.Replace(sanitized, "[REDACTED]");
            sanitized = Regex.Replace(sanitized, "\\s+", " ").Trim();
            return sanitized.Length <= 1024 ? sanitized : sanitized.Substring(0, 1024);
        }
    }
}
