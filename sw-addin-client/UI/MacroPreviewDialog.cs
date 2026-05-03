using System;
using System.Drawing;
using System.Windows.Forms;

namespace SwCopilotAddin.UI
{
    public sealed class MacroPreviewDialog : Form
    {
        public MacroPreviewDialog(string macroCode, string statusMessage)
        {
            Text = "Review Macro Before Execution";
            StartPosition = FormStartPosition.CenterParent;
            Width = 900;
            Height = 700;
            MinimumSize = new Size(640, 420);
            BackColor = Color.FromArgb(0x1E, 0x1E, 0x2E);

            var warning = new Label
            {
                Dock = DockStyle.Top,
                Height = 72,
                Padding = new Padding(12, 10, 12, 8),
                BackColor = Color.FromArgb(0x18, 0x18, 0x25),
                ForeColor = Color.FromArgb(0xFA, 0xE3, 0xB0),
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                Text = "Security review required. This generated macro will run inside SolidWorks with your user permissions. " +
                       "Review the code and click Run only if you trust it.\r\n\r\n" +
                       (string.IsNullOrWhiteSpace(statusMessage) ? "Generated macro" : statusMessage),
            };

            var codeBox = new RichTextBox
            {
                Dock = DockStyle.Fill,
                ReadOnly = true,
                WordWrap = false,
                BorderStyle = BorderStyle.None,
                BackColor = Color.FromArgb(0x11, 0x11, 0x1B),
                ForeColor = Color.FromArgb(0xCD, 0xD6, 0xF4),
                Font = new Font("Consolas", 9),
                ScrollBars = RichTextBoxScrollBars.Both,
                Text = macroCode ?? string.Empty,
            };

            var buttons = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom,
                Height = 56,
                FlowDirection = FlowDirection.RightToLeft,
                Padding = new Padding(8),
                BackColor = Color.FromArgb(0x18, 0x18, 0x25),
            };

            var runButton = new Button
            {
                Text = "Run",
                Width = 110,
                Height = 34,
                DialogResult = DialogResult.OK,
                BackColor = Color.FromArgb(0xA6, 0xE3, 0xA1),
                ForeColor = Color.FromArgb(0x1E, 0x1E, 0x2E),
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
            };
            runButton.FlatAppearance.BorderSize = 0;

            var cancelButton = new Button
            {
                Text = "Cancel",
                Width = 110,
                Height = 34,
                DialogResult = DialogResult.Cancel,
                BackColor = Color.FromArgb(0xF3, 0x8B, 0xA8),
                ForeColor = Color.FromArgb(0x1E, 0x1E, 0x2E),
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
            };
            cancelButton.FlatAppearance.BorderSize = 0;

            CancelButton = cancelButton;

            buttons.Controls.Add(runButton);
            buttons.Controls.Add(cancelButton);

            Controls.Add(codeBox);
            Controls.Add(buttons);
            Controls.Add(warning);
        }
    }
}
