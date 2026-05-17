using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
using SolidWorks.Interop.swpublished;

namespace SwCopilotAddin.AddinCore
{
    [ComVisible(true)]
    [Guid(AddinInfo.AddinGuid)]
    [ProgId(AddinInfo.ProgId)]
    public class SwAddin : ISwAddin
    {
        private ISldWorks? _swApp;
        private int _addinCookie;
        private ITaskpaneView? _taskPaneView;
        private UI.TaskPaneHost? _taskPaneHost;

        // ── ISwAddin ──────────────────────────────────────────────────────────

        public SwAddin()
        {
            Log("SwAddin constructed.");
        }

        public bool ConnectToSW(object ThisSW, int Cookie)
        {
            try
            {
                Log("ConnectToSW started.");
                _swApp       = (ISldWorks)ThisSW;
                _addinCookie = Cookie;

                // Required so SolidWorks can route callbacks back into this addin.
                _swApp.SetAddinCallbackInfo2(0, this, Cookie);

                // Quiet mode: suppress the "Modify value" dialog that SolidWorks
                // pops up every time IAddDiameterDimension2 / IAddLinearDimension
                // fires. The agent always knows the exact value it wants — there
                // is no human to confirm. This is global to the SW session.
                try
                {
                    _swApp.SetUserPreferenceToggle(
                        (int)swUserPreferenceToggle_e.swInputDimValOnCreate, false);
                }
                catch (Exception toggleEx)
                {
                    Log("Failed to suppress input-dim-value dialog: " + toggleEx.Message);
                }

                AddTaskPane();
                Log("ConnectToSW completed.");
                return true;
            }
            catch (Exception ex)
            {
                Log("ConnectToSW failed: " + ex);
                return false;
            }
        }

        public bool DisconnectFromSW()
        {
            _taskPaneView?.DeleteView();
            if (_taskPaneView != null)
            {
                Marshal.ReleaseComObject(_taskPaneView);
                _taskPaneView = null;
            }
            _taskPaneHost?.Dispose();
            _taskPaneHost = null;
            return true;
        }

        // ── Task Pane ─────────────────────────────────────────────────────────

        private void AddTaskPane()
        {
            string iconPath = EnsureTaskPaneIcon();
            Log("Creating task pane with icon: " + iconPath);
            if (_swApp == null)
                throw new InvalidOperationException("SolidWorks application is not connected.");

            _taskPaneView = _swApp.CreateTaskpaneView2(iconPath, AddinInfo.AddinTitle);
            if (_taskPaneView == null)
                throw new InvalidOperationException("SolidWorks returned null from CreateTaskpaneView2.");

            Log("Task pane view created.");

            _taskPaneHost = new UI.TaskPaneHost(_swApp);
            _taskPaneHost.CreateControl();
            Log("Task pane host created. Host handle: " + _taskPaneHost.Handle);

            _taskPaneView.DisplayWindowFromHandlex64(_taskPaneHost.Handle.ToInt64());
            Log("Task pane displayed. Host handle: " + _taskPaneHost.Handle);
        }

        // ── COM Registration ──────────────────────────────────────────────────
        // These static methods are called by regasm when the DLL is registered/
        // unregistered. They write the SolidWorks discovery key into HKLM so
        // SolidWorks 2021 picks up the addin on next launch.

        private static string AppDataDirectory
        {
            get
            {
                string root = System.Environment.GetFolderPath(
                    System.Environment.SpecialFolder.LocalApplicationData);
                string dir = Path.Combine(root, "SwCopilotAddin");
                Directory.CreateDirectory(dir);
                return dir;
            }
        }

        private static string EnsureTaskPaneIcon()
        {
            string iconPath = Path.Combine(AppDataDirectory, "taskpane.bmp");
            if (File.Exists(iconPath))
                return iconPath;

            using var bmp = new Bitmap(16, 18);
            using Graphics g = Graphics.FromImage(bmp);
            g.Clear(Color.White);
            using var border = new Pen(Color.FromArgb(80, 200, 180), 2);
            using var accent = new SolidBrush(Color.FromArgb(80, 200, 180));
            using var text = new SolidBrush(Color.Black);
            using var font = new Font(FontFamily.GenericSansSerif, 6, FontStyle.Bold);

            g.DrawRectangle(border, 1, 1, 13, 15);
            g.FillEllipse(accent, 10, 2, 5, 5);
            g.DrawString("SW", font, text, 1, 7);
            bmp.Save(iconPath, ImageFormat.Bmp);

            return iconPath;
        }

        private static void Log(string message)
        {
            try
            {
                string path = Path.Combine(AppDataDirectory, "addin.log");
                File.AppendAllText(
                    path,
                    $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {message}{System.Environment.NewLine}");
            }
            catch
            {
                // Logging must never prevent SolidWorks from loading the add-in.
            }
        }

        [ComRegisterFunction]
        public static void RegisterFunction(Type t)
        {
            string keyPath = $@"SOFTWARE\SolidWorks\AddIns\{{{AddinInfo.AddinGuid}}}";
            using RegistryKey? hklm = Registry.LocalMachine.CreateSubKey(keyPath);
            if (hklm == null)
                throw new InvalidOperationException("Could not create SolidWorks add-in registry key.");
            hklm.SetValue(null,            1);                          // 1 = load on startup
            hklm.SetValue("Title",         AddinInfo.AddinTitle);
            hklm.SetValue("Description",   AddinInfo.AddinDescription);
        }

        [ComUnregisterFunction]
        public static void UnregisterFunction(Type t)
        {
            Registry.LocalMachine.DeleteSubKey(
                $@"SOFTWARE\SolidWorks\AddIns\{{{AddinInfo.AddinGuid}}}",
                throwOnMissingSubKey: false);
        }
    }
}
