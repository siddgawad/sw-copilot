using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using SolidWorks.Interop.sldworks;
using SwCopilotAddin.Client;
using SwCopilotAddin.Execution;

namespace SwCopilotAddin.UI
{
    /// <summary>
    /// Native WinForms task pane. This avoids WPF keyboard-focus issues inside
    /// the SolidWorks task pane host.
    /// </summary>
    public sealed class TaskPaneHost : UserControl
    {
        private readonly ISldWorks _swApp;
        private readonly BackendClient _client;
        private readonly DocumentContextBuilder _contextBuilder;
        private readonly OperationExecutor _operationExecutor;
        private readonly List<ConversationMessage> _history = new List<ConversationMessage>();

        private readonly RichTextBox _messages;
        private readonly Label _status;
        private readonly TextBox _input;
        private readonly Button _sendButton;
        private readonly Button _undoButton;
        private string? _lastOperationRuntimeForHistory;

        private const int MaxAutoRepairAttempts = 2;
        private const int MaxHistoryMessages = 8;
        private const int MaxHistoryContentChars = 3000;
        private const int MaxRuntimeHistoryChars = 1400;
        private static readonly bool AllowLegacyMacroFallback =
            string.Equals(
                System.Environment.GetEnvironmentVariable("SW_COPILOT_ALLOW_LEGACY_MACROS"),
                "1",
                StringComparison.Ordinal);

        public TaskPaneHost(ISldWorks swApp)
        {
            _swApp = swApp;
            _client = new BackendClient();
            _contextBuilder = new DocumentContextBuilder(swApp);
            _operationExecutor = new OperationExecutor(swApp);

            BackColor = Color.FromArgb(0x1E, 0x1E, 0x2E);
            Dock = DockStyle.Fill;

            var header = new Label
            {
                Text = "SW Copilot",
                Dock = DockStyle.Top,
                Height = 42,
                Padding = new Padding(12, 10, 0, 0),
                BackColor = Color.FromArgb(0x18, 0x18, 0x25),
                ForeColor = Color.FromArgb(0xCB, 0xA6, 0xF7),
                Font = new Font("Segoe UI", 12, FontStyle.Bold),
            };

            _messages = new RichTextBox
            {
                Dock = DockStyle.Fill,
                ReadOnly = true,
                BorderStyle = BorderStyle.None,
                BackColor = Color.FromArgb(0x1E, 0x1E, 0x2E),
                ForeColor = Color.FromArgb(0xCD, 0xD6, 0xF4),
                Font = new Font("Segoe UI", 9),
                ScrollBars = RichTextBoxScrollBars.Vertical,
                TabStop = false,
            };

            _status = new Label
            {
                Text = "Ready",
                Dock = DockStyle.Top,
                Height = 22,
                Padding = new Padding(10, 4, 0, 0),
                ForeColor = Color.FromArgb(0xA6, 0xAD, 0xC8),
                BackColor = Color.FromArgb(0x1E, 0x1E, 0x2E),
                Font = new Font("Segoe UI", 8),
            };

            _input = new TextBox
            {
                Dock = DockStyle.Fill,
                BorderStyle = BorderStyle.FixedSingle,
                BackColor = Color.FromArgb(0x31, 0x32, 0x44),
                ForeColor = Color.FromArgb(0xCD, 0xD6, 0xF4),
                Font = new Font("Segoe UI", 10),
                TabIndex = 0,
            };
            _input.KeyDown += async (_, e) =>
            {
                if (e.KeyCode == Keys.Enter)
                {
                    e.SuppressKeyPress = true;
                    await SubmitAsync();
                }
            };

            _sendButton = new Button
            {
                Text = "Send",
                Dock = DockStyle.Right,
                Width = 82,
                BackColor = Color.FromArgb(0x89, 0xB4, 0xFA),
                ForeColor = Color.FromArgb(0x1E, 0x1E, 0x2E),
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                TabIndex = 1,
            };
            _sendButton.FlatAppearance.BorderSize = 0;
            _sendButton.Click += async (_, _) => await SubmitAsync();

            _undoButton = new Button
            {
                Text = "Undo Last",
                Dock = DockStyle.Right,
                Width = 96,
                BackColor = Color.FromArgb(0x45, 0x45, 0x5E),
                ForeColor = Color.FromArgb(0xCD, 0xD6, 0xF4),
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                TabIndex = 2,
            };
            _undoButton.FlatAppearance.BorderSize = 0;
            _undoButton.Click += (_, _) => RollbackLastExecute();

            var inputRow = new Panel
            {
                Dock = DockStyle.Fill,
                Padding = new Padding(8, 4, 8, 8),
                BackColor = Color.FromArgb(0x1E, 0x1E, 0x2E),
            };
            inputRow.Controls.Add(_input);
            inputRow.Controls.Add(_undoButton);
            inputRow.Controls.Add(_sendButton);

            var bottom = new Panel
            {
                Dock = DockStyle.Bottom,
                Height = 82,
                BackColor = Color.FromArgb(0x1E, 0x1E, 0x2E),
            };
            bottom.Controls.Add(inputRow);
            bottom.Controls.Add(_status);

            Controls.Add(_messages);
            Controls.Add(bottom);
            Controls.Add(header);

            Load += (_, _) => BeginInvoke((Action)(() => _input.Focus()));
            Click += (_, _) => _input.Focus();
        }

        private async Task SubmitAsync()
        {
            string prompt = _input.Text.Trim();
            if (string.IsNullOrEmpty(prompt))
            {
                _input.Focus();
                return;
            }

            _input.Clear();
            AppendMessage("You", prompt);
            SetStatus("Contacting agent...");
            _sendButton.Enabled = false;
            _undoButton.Enabled = false;
            _lastOperationRuntimeForHistory = null;

            try
            {
                DocumentContext ctx = _contextBuilder.Build();
                AgentResponse response = await _client.SendPromptAsync(prompt, ctx, _history);

                AppendMessage("Agent", response.StatusMessage);

                if (response.OperationGraph != null)
                {
                    AgentResponse? executedResponse = await ExecuteOperationGraphWithRepairAsync(prompt, ctx, response);
                    if (executedResponse == null)
                        return;
                    response = executedResponse;
                }
                else if (response.CadCommand.HasValue)
                {
                    CadCommandDto command = response.CadCommand.Value;
                    string commandJson = JsonConvert.SerializeObject(command, Formatting.Indented);

                    SetStatus("Waiting for command review...");
                    using (var preview = new MacroPreviewDialog(commandJson, response.StatusMessage))
                    {
                        if (preview.ShowDialog(this) != DialogResult.OK)
                        {
                            const string cancelled = "Execution cancelled by user. CAD command was not run.";
                            SetStatus("Ready");
                            AppendMessage("Runtime", cancelled);
                            return;
                        }
                    }

                    SetStatus("Executing CAD command...");
                    var executor = new CadCommandExecutor(_swApp);
                    string result = executor.Execute(command);
                    SetStatus(result);
                    AppendMessage("Runtime", result);
                }
                else if (!string.IsNullOrEmpty(response.MacroCode))
                {
                    if (!AllowLegacyMacroFallback)
                    {
                        const string blocked = "Blocked legacy macro response. This build only executes validated operation_graph JSON. Set SW_COPILOT_ALLOW_LEGACY_MACROS=1 to re-enable the Roslyn fallback for local development.";
                        SetStatus("Blocked legacy macro");
                        AppendMessage("Runtime", blocked);
                    }
                    else
                    {
                        SetStatus("Waiting for macro review...");
                        string macroCode = response.MacroCode!;
                        using (var preview = new MacroPreviewDialog(macroCode, response.StatusMessage))
                        {
                            if (preview.ShowDialog(this) != DialogResult.OK)
                            {
                                const string cancelled = "Execution cancelled by user. Macro was not run.";
                                SetStatus("Ready");
                                AppendMessage("Runtime", cancelled);
                                return;
                            }
                        }

                        SetStatus("Executing macro...");
                        var executor = new MacroExecutor(_swApp);
                        string result = executor.Execute(macroCode);
                        SetStatus(result);
                        AppendMessage("Runtime", result);
                    }
                }
                else
                {
                    SetStatus("Ready");
                }

                // Record the exchange so subsequent prompts have dimension context.
                _history.Add(new ConversationMessage("user", prompt));
                _history.Add(new ConversationMessage(
                    "assistant",
                    BuildAssistantHistoryContent(response, _lastOperationRuntimeForHistory)));
                PruneHistory();
            }
            catch (Exception ex)
            {
                AppendMessage("Error", ex.Message);
                SetStatus("Error - check the message above");
            }
            finally
            {
                _sendButton.Enabled = true;
                _undoButton.Enabled = true;
                _input.Focus();
            }
        }

        private async Task<AgentResponse?> ExecuteOperationGraphWithRepairAsync(
            string prompt,
            DocumentContext ctx,
            AgentResponse initialResponse)
        {
            AgentResponse currentResponse = initialResponse;
            var repairHistory = new List<ConversationMessage>(_history)
            {
                new ConversationMessage("user", prompt),
            };

            for (int repairAttempt = 0; ; repairAttempt++)
            {
                OperationGraphDto? graph = currentResponse.OperationGraph;
                if (graph == null)
                {
                    const string noGraph = "ERROR: Repair response did not include an operation_graph. Execution stopped.";
                    SetStatus("Error - see message above");
                    AppendMessage("Runtime", noGraph);
                    _lastOperationRuntimeForHistory = noGraph;
                    return currentResponse;
                }

                string preview = FormatOperationPlan(graph, currentResponse.StatusMessage);
                SetStatus(repairAttempt == 0
                    ? "Review operation plan..."
                    : $"Review repaired plan ({repairAttempt}/{MaxAutoRepairAttempts})...");

                using (var dlg = new MacroPreviewDialog(preview, currentResponse.StatusMessage))
                {
                    if (dlg.ShowDialog(this) != DialogResult.OK)
                    {
                        SetStatus("Ready");
                        AppendMessage("Runtime", "Execution cancelled by user.");
                        return null;
                    }
                }

                if (graph.MissingInputs != null && graph.MissingInputs.Length > 0)
                {
                    string ask = "Please provide:\n• " + string.Join("\n• ", graph.MissingInputs);
                    SetStatus("Needs clarification");
                    AppendMessage("Agent", ask);
                    return null;
                }

                SetStatus(repairAttempt == 0
                    ? "Executing operation plan..."
                    : $"Executing repaired plan ({repairAttempt}/{MaxAutoRepairAttempts})...");

                string result = _operationExecutor.Execute(graph);
                _lastOperationRuntimeForHistory = result;
                AppendMessage("Runtime", result);

                repairHistory.Add(new ConversationMessage(
                    "assistant",
                    BuildAssistantHistoryContent(currentResponse, result)));

                if (!IsRepairableExecutionFailure(result))
                {
                    string validationStatus = await ValidateExecutionResultAsync(graph, result);
                    SetStatus(validationStatus);
                    return currentResponse;
                }

                if (repairAttempt >= MaxAutoRepairAttempts)
                {
                    SetStatus("Error - auto-repair exhausted");
                    AppendMessage("Agent", $"Automatic repair stopped after {MaxAutoRepairAttempts} failed attempts.");
                    return currentResponse;
                }

                int nextAttempt = repairAttempt + 1;
                SetStatus($"Requesting repair {nextAttempt}/{MaxAutoRepairAttempts}...");
                AppendMessage("Agent", $"Execution failed. Requesting automatic repair {nextAttempt}/{MaxAutoRepairAttempts}...");
                currentResponse = await _client.SendPromptAsync(prompt, ctx, repairHistory);
                AppendMessage("Agent", currentResponse.StatusMessage);
            }
        }

        private static bool IsRepairableExecutionFailure(string result)
        {
            if (result.IndexOf("RULE VIOLATION", StringComparison.OrdinalIgnoreCase) >= 0)
                return false;

            if (result.IndexOf("ERROR: Hole cut failed", StringComparison.OrdinalIgnoreCase) >= 0)
                return false;

            return result.IndexOf("ERROR:", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static string BuildAssistantHistoryContent(AgentResponse response, string? runtimeResult = null)
        {
            var sb = new StringBuilder();
            if (!string.IsNullOrWhiteSpace(response.StatusMessage))
                sb.AppendLine(response.StatusMessage.Trim());

            if (response.OperationGraph != null)
            {
                sb.AppendLine("OperationGraph:");
                sb.AppendLine(JsonConvert.SerializeObject(response.OperationGraph, Formatting.None));
            }

            string runtimeSummary = BuildRuntimeHistorySummary(runtimeResult);
            if (!string.IsNullOrWhiteSpace(runtimeSummary))
            {
                sb.AppendLine("Runtime:");
                sb.AppendLine(runtimeSummary);
            }

            return TrimForHistory(sb.ToString().TrimEnd(), MaxHistoryContentChars);
        }

        private static string BuildRuntimeHistorySummary(string? runtimeResult)
        {
            if (string.IsNullOrWhiteSpace(runtimeResult))
                return string.Empty;

            string nonNullRuntime = runtimeResult!;
            string visibleRuntime = RemovePartReportLine(nonNullRuntime).Trim();
            string? reportJson = ExtractPartReportJson(nonNullRuntime);
            string reportSummary = FormatPartReportSummary(reportJson);

            if (IsRepairableExecutionFailure(nonNullRuntime))
                return TrimForHistory(visibleRuntime, MaxRuntimeHistoryChars);

            var sb = new StringBuilder();
            if (!string.IsNullOrWhiteSpace(visibleRuntime))
                sb.AppendLine(TrimForHistory(visibleRuntime, MaxRuntimeHistoryChars));
            if (!string.IsNullOrWhiteSpace(reportSummary))
                sb.AppendLine(reportSummary);

            return sb.ToString().TrimEnd();
        }

        private static string RemovePartReportLine(string runtimeResult)
        {
            const string marker = "Runtime (report): ";
            var sb = new StringBuilder();
            string[] lines = runtimeResult.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None);
            foreach (string line in lines)
            {
                if (!line.StartsWith(marker, StringComparison.Ordinal))
                    sb.AppendLine(line);
            }
            return sb.ToString().TrimEnd();
        }

        private static string FormatPartReportSummary(string? partReportJson)
        {
            if (string.IsNullOrWhiteSpace(partReportJson))
                return string.Empty;

            string nonNullJson = partReportJson!;
            try
            {
                JObject report = JObject.Parse(nonNullJson);
                string bodyCount = report["body_count"]?.ToString() ?? "?";
                string featureCount = report["feature_count"]?.ToString() ?? "?";
                JObject? bbox = report["bounding_box"] as JObject;
                string bboxText = "none";
                if (bbox != null)
                {
                    bboxText =
                        $"{FormatMm(bbox["x_mm"])} x {FormatMm(bbox["y_mm"])} x {FormatMm(bbox["z_mm"])}";
                }

                return $"PartReport: body_count={bodyCount}; bbox_mm={bboxText}; feature_count={featureCount}";
            }
            catch
            {
                return string.Empty;
            }
        }

        private static string FormatMm(JToken? value)
        {
            double? number = value?.Value<double?>();
            return number.HasValue
                ? number.Value.ToString("0.###", CultureInfo.InvariantCulture)
                : "?";
        }

        private static string TrimForHistory(string value, int maxChars)
        {
            if (value.Length <= maxChars)
                return value;
            return value.Substring(0, maxChars) + "\n... [history truncated]";
        }

        private void PruneHistory()
        {
            int excess = _history.Count - MaxHistoryMessages;
            if (excess > 0)
                _history.RemoveRange(0, excess);
        }

        private async Task<string> ValidateExecutionResultAsync(OperationGraphDto graph, string runtimeResult)
        {
            string? partReportJson = ExtractPartReportJson(runtimeResult);
            if (string.IsNullOrWhiteSpace(partReportJson))
                return "Done";

            try
            {
                ValidationResponse validation = await _client.ValidateOperationAsync(graph, partReportJson!);
                AppendMessage("Validation", FormatValidationReport(validation));

                if (!validation.Passed)
                    return "Done - validation errors";
                return validation.HasWarnings ? "Done - validation warnings" : "Done";
            }
            catch (Exception ex)
            {
                AppendMessage("Validation", "Validation skipped: " + ex.Message);
                return "Done - validation skipped";
            }
        }

        private static string? ExtractPartReportJson(string runtimeResult)
        {
            const string marker = "Runtime (report): ";
            string[] lines = runtimeResult.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None);
            foreach (string line in lines)
            {
                if (line.StartsWith(marker, StringComparison.Ordinal))
                    return line.Substring(marker.Length).Trim();
            }

            return null;
        }

        private static string FormatValidationReport(ValidationResponse validation)
        {
            if (validation.Passed && !validation.HasWarnings)
                return "Passed. SolidWorks part report matches the requested operation graph within tolerance.";

            var sb = new StringBuilder();
            sb.AppendLine(validation.Passed ? "Passed with warnings." : "Failed.");

            foreach (ValidationDiscrepancy discrepancy in validation.Discrepancies ?? System.Array.Empty<ValidationDiscrepancy>())
            {
                sb.AppendLine(
                    $"[{discrepancy.Severity}] {discrepancy.Category}: {discrepancy.Message}");

                if (!string.IsNullOrWhiteSpace(discrepancy.Expected) ||
                    !string.IsNullOrWhiteSpace(discrepancy.Actual))
                {
                    sb.AppendLine($"  expected: {discrepancy.Expected}");
                    sb.AppendLine($"  actual:   {discrepancy.Actual}");
                }
            }

            return sb.ToString().TrimEnd();
        }

        private void RollbackLastExecute()
        {
            SetStatus("Undoing last execution...");
            _undoButton.Enabled = false;

            try
            {
                string result = _operationExecutor.RollbackLastExecute();
                SetStatus(result.StartsWith("ERROR", StringComparison.OrdinalIgnoreCase) ? "Undo failed" : "Ready");
                AppendMessage("Runtime", result);
            }
            catch (Exception ex)
            {
                SetStatus("Undo failed");
                AppendMessage("Error", ex.Message);
            }
            finally
            {
                _undoButton.Enabled = true;
                _input.Focus();
            }
        }

        private void AppendMessage(string sender, string text)
        {
            _messages.SelectionStart = _messages.TextLength;
            _messages.SelectionColor = sender == "You"
                ? Color.FromArgb(0x89, 0xB4, 0xFA)
                : Color.FromArgb(0xCB, 0xA6, 0xF7);
            _messages.AppendText(sender + ":\r\n");
            _messages.SelectionColor = Color.FromArgb(0xCD, 0xD6, 0xF4);
            _messages.AppendText(text + "\r\n\r\n");
            _messages.ScrollToCaret();
        }

        private void SetStatus(string message)
        {
            _status.Text = message;
        }

        private static string FormatOperationPlan(OperationGraphDto graph, string statusMsg)
        {
            var sb = new StringBuilder();
            if (!string.IsNullOrWhiteSpace(graph.PartName))
                sb.AppendLine("PART: " + graph.PartName);

            if (graph.MissingInputs?.Length > 0)
            {
                sb.AppendLine();
                sb.AppendLine("MISSING INFORMATION (clarify before executing):");
                foreach (string m in graph.MissingInputs)
                    sb.AppendLine("  * " + m);
            }

            if (graph.Assumptions?.Length > 0)
            {
                sb.AppendLine();
                sb.AppendLine("ASSUMPTIONS:");
                foreach (string a in graph.Assumptions)
                    sb.AppendLine("  * " + a);
            }

            sb.AppendLine();
            sb.AppendLine($"OPERATIONS ({graph.Operations?.Length ?? 0}):");
            int n = 1;
            foreach (OperationDto op in graph.Operations ?? System.Array.Empty<OperationDto>())
                sb.AppendLine($"  {n++,2}. [{op.Id}] {DescribeOp(op)}");

            return sb.ToString().TrimEnd();
        }

        private static string DescribeOp(OperationDto op)
        {
            switch ((op.Type ?? "").ToLowerInvariant())
            {
                case "sketch":
                    return $"Sketch on {op.Plane ?? "Top Plane"} — {op.Entities?.Length ?? 0} entit(ies)";
                case "extrude_boss":
                    return $"Extrude Boss from '{op.ProfileId}', {op.DepthMm:0.#} mm" +
                           (string.IsNullOrEmpty(op.Name) ? "" : $" → \"{op.Name}\"");
                case "extrude_cut":
                    return op.ThroughAll
                        ? $"Extrude Cut through all from '{op.ProfileId}'"
                        : $"Extrude Cut {op.DepthMm:0.#} mm from '{op.ProfileId}'";
                case "fillet":
                    string fTarget = op.FeatureIds?.Length > 0
                        ? string.Join(", ", op.FeatureIds) : "all features";
                    return $"Fillet R={op.RadiusMm:0.#} mm on {fTarget}";
                case "chamfer":
                    string cTarget = op.FeatureIds?.Length > 0
                        ? string.Join(", ", op.FeatureIds) : "all features";
                    return $"Chamfer {op.DistanceMm:0.#} mm on {cTarget}";
                case "hole_wizard":
                    return $"Holes: {op.Positions?.Length ?? 0}× {op.FastenerSize} {op.HoleType} on '{op.FaceOf}'";
                case "circular_pattern":
                    return $"Circular pattern {op.Count}× on Ø{op.PcdMm:0.#} mm PCD";
                case "linear_pattern":
                    return $"Linear pattern {op.Dir1Count ?? 1}×{op.Dir2Count ?? 1}";
                case "mirror":
                    return $"Mirror about {op.MirrorPlane ?? "Right Plane"}";
                case "revolve":
                    return $"Revolve {op.AngleDeg ?? 360:0.#}° from '{op.ProfileId}'";
                case "delete_feature":
                    if (op.LastN.HasValue) return $"Delete last {op.LastN} feature(s)";
                    if (op.FeatureIds?.Length > 0) return "Delete: " + string.Join(", ", op.FeatureIds);
                    return "Delete all features";
                case "noop":
                    return op.Message ?? "No operation";
                default:
                    return op.Type ?? "unknown";
            }
        }
    }
}
